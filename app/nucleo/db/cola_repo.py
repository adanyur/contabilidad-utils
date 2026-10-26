"""Cola de trabajos sobre pgmq + estado visible en nucleo.trabajo.

pgmq solo transporta el aviso {"trabajo_id": N}. El estado, el progreso y el historial
que ve el usuario viven en nucleo.trabajo.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.nucleo.modelos import Trabajo

CANAL_AVANCE = "trabajo_avance"

_SELECT_TRABAJO = """
SELECT t.id, t.proceso_codigo, t.empresa_id, t.periodo, t.carga_archivo_id, t.parametros,
       t.estado, t.progreso, t.mensaje, t.intentos, t.max_intentos, t.msg_id,
       t.creado_en, t.finalizado_en, e.ruc AS empresa_ruc, e.razon_social AS empresa_nombre
  FROM nucleo.trabajo t
  JOIN nucleo.empresa e ON e.id = t.empresa_id
"""


@dataclass(frozen=True)
class Mensaje:
    msg_id: int
    read_ct: int
    trabajo_id: int


# --- lado de la UI -------------------------------------------------------------------------

async def encolar(
    conn: AsyncConnection,
    proceso_codigo: str,
    empresa_id: int,
    periodo: str,
    carga_archivo_id: Optional[int],
    parametros: dict[str, Any],
    max_intentos: int,
    usuario: Optional[str],
) -> int:
    """Crea el trabajo y lo envía a la cola del proceso. Debe ir en la misma transacción que la carga."""
    cur = await conn.execute(
        """
        INSERT INTO nucleo.trabajo
            (proceso_codigo, empresa_id, periodo, carga_archivo_id, parametros, max_intentos, usuario)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (proceso_codigo, empresa_id, periodo, carga_archivo_id, Jsonb(parametros), max_intentos, usuario),
    )
    trabajo_id = (await cur.fetchone())["id"]
    await _enviar(conn, proceso_codigo, trabajo_id)
    await _avisar(conn, trabajo_id)
    return trabajo_id


async def reintentar(conn: AsyncConnection, trabajo_id: int) -> bool:
    cur = await conn.execute(
        """
        UPDATE nucleo.trabajo
           SET estado = 'PENDIENTE', progreso = 0, mensaje = 'Reencolado', intentos = 0, finalizado_en = NULL
         WHERE id = %s AND estado IN ('ERROR', 'CANCELADO')
        RETURNING proceso_codigo
        """,
        (trabajo_id,),
    )
    fila = await cur.fetchone()
    if fila is None:
        return False
    await _enviar(conn, fila["proceso_codigo"], trabajo_id)
    await _avisar(conn, trabajo_id)
    return True


async def cancelar(conn: AsyncConnection, trabajo_id: int) -> bool:
    """Solo se cancela lo que aún no empezó; el worker descarta el mensaje al leerlo."""
    cur = await conn.execute(
        """
        UPDATE nucleo.trabajo
           SET estado = 'CANCELADO', mensaje = 'Cancelado por el usuario', finalizado_en = now()
         WHERE id = %s AND estado = 'PENDIENTE'
        """,
        (trabajo_id,),
    )
    if cur.rowcount:
        await _avisar(conn, trabajo_id)
    return cur.rowcount > 0


async def listar(conn: AsyncConnection, limite: int = 50, proceso_codigo: Optional[str] = None) -> list[Trabajo]:
    sql = _SELECT_TRABAJO
    params: list = []
    if proceso_codigo:
        sql += " WHERE t.proceso_codigo = %s"
        params.append(proceso_codigo)
    sql += " ORDER BY t.id DESC LIMIT %s"
    params.append(limite)
    cur = await conn.execute(sql, params)
    return [Trabajo(**f) for f in await cur.fetchall()]


async def obtener(conn: AsyncConnection, trabajo_id: int) -> Optional[Trabajo]:
    cur = await conn.execute(_SELECT_TRABAJO + " WHERE t.id = %s", (trabajo_id,))
    fila = await cur.fetchone()
    return Trabajo(**fila) if fila else None


# --- lado del worker -----------------------------------------------------------------------

async def leer(conn: AsyncConnection, cola: str, vt: int, espera_seg: int) -> Optional[Mensaje]:
    """Espera hasta espera_seg un mensaje; mientras se procesa queda invisible vt segundos."""
    cur = await conn.execute(
        "SELECT msg_id, read_ct, message FROM pgmq.read_with_poll(%s, %s, 1, %s, 250)",
        (cola, vt, espera_seg),
    )
    fila = await cur.fetchone()
    if fila is None:
        return None
    return Mensaje(fila["msg_id"], fila["read_ct"], int(fila["message"]["trabajo_id"]))


async def extender(conn: AsyncConnection, cola: str, msg_id: int, vt: int) -> None:
    await conn.execute("SELECT pgmq.set_vt(%s, %s, %s)", (cola, msg_id, vt))


async def archivar(conn: AsyncConnection, cola: str, msg_id: int) -> None:
    await conn.execute("SELECT pgmq.archive(%s, %s::bigint)", (cola, msg_id))


async def marcar_en_proceso(conn: AsyncConnection, trabajo_id: int, msg_id: int, intento: int, worker_id: str) -> None:
    await conn.execute(
        """
        UPDATE nucleo.trabajo
           SET estado = 'EN_PROCESO', progreso = 0, mensaje = 'Iniciando', intentos = %s, msg_id = %s,
               worker_id = %s, iniciado_en = now(), heartbeat_en = now(), finalizado_en = NULL
         WHERE id = %s
        """,
        (intento, msg_id, worker_id, trabajo_id),
    )
    await _avisar(conn, trabajo_id)


async def latido(conn: AsyncConnection, trabajo_id: int) -> None:
    await conn.execute("UPDATE nucleo.trabajo SET heartbeat_en = now() WHERE id = %s", (trabajo_id,))


async def avance(conn: AsyncConnection, trabajo_id: int, progreso: int, mensaje: str) -> None:
    await conn.execute(
        "UPDATE nucleo.trabajo SET progreso = %s, mensaje = %s, heartbeat_en = now() WHERE id = %s",
        (progreso, mensaje, trabajo_id),
    )
    await _avisar(conn, trabajo_id)


async def finalizar(conn: AsyncConnection, trabajo_id: int, estado: str, mensaje: str) -> None:
    """estado OK/ERROR termina el trabajo; PENDIENTE lo deja a la espera del reintento."""
    await conn.execute(
        """
        UPDATE nucleo.trabajo
           SET estado = %s,
               progreso = CASE WHEN %s::text = 'OK' THEN 100 ELSE progreso END,
               mensaje = %s,
               finalizado_en = CASE WHEN %s::text IN ('OK', 'ERROR') THEN now() END
         WHERE id = %s
        """,
        (estado, estado, mensaje, estado, trabajo_id),
    )
    await _avisar(conn, trabajo_id)


# --- internos ------------------------------------------------------------------------------

async def _enviar(conn: AsyncConnection, proceso_codigo: str, trabajo_id: int) -> None:
    cur = await conn.execute("SELECT cola FROM nucleo.proceso WHERE codigo = %s", (proceso_codigo,))
    proceso = await cur.fetchone()
    if proceso is None:
        raise ValueError(f"Proceso desconocido: {proceso_codigo}")
    cur = await conn.execute(
        "SELECT * FROM pgmq.send(%s, %s::jsonb) AS s(msg_id)",
        (proceso["cola"], json.dumps({"trabajo_id": trabajo_id})),
    )
    msg_id = (await cur.fetchone())["msg_id"]
    await conn.execute("UPDATE nucleo.trabajo SET msg_id = %s WHERE id = %s", (msg_id, trabajo_id))


async def _avisar(conn: AsyncConnection, trabajo_id: int) -> None:
    # NOTIFY se entrega al confirmar la transacción
    await conn.execute("SELECT pg_notify(%s, %s)", (CANAL_AVANCE, str(trabajo_id)))
