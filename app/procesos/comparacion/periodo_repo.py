"""Cabecera por empresa + periodo, sustento de comprobantes y cierre (schema comparacion)."""

from typing import Optional

from psycopg import AsyncConnection

ABIERTO, CERRADO = "ABIERTO", "CERRADO"
PENDIENTE, SUSTENTADO, EN_CORRECCION = "PENDIENTE", "SUSTENTADO", "EN_CORRECCION"
ESTADOS_SUSTENTO = {PENDIENTE: "Pendiente", SUSTENTADO: "Sustentado", EN_CORRECCION: "En corrección"}
MOTIVO_RECHAZADO = "RECHAZADO_SUNAT"

# Comprobantes que impiden cerrar: requieren sustento y no están SUSTENTADO
_PENDIENTE_SQL = "d.requiere_sustento AND coalesce(s.estado, 'PENDIENTE') <> 'SUSTENTADO'"

_SELECT_PERIODO = f"""
SELECT p.id, p.empresa_id, p.periodo, p.estado, p.trabajo_vigente_id, p.actualizado_en, p.cerrado_en, p.cerrado_por,
       e.ruc AS empresa_ruc, e.razon_social AS empresa_nombre,
       tv.finalizado_en AS vigente_en,
       (SELECT count(*) FROM comparacion.periodo_evento ev WHERE ev.periodo_id = p.id AND ev.tipo = 'CARGA') AS cargas,
       (SELECT count(*) FROM comparacion.detalle d
         WHERE d.trabajo_id = p.trabajo_vigente_id AND d.requiere_sustento) AS requieren_sustento,
       (SELECT count(*) FROM comparacion.detalle d
          LEFT JOIN comparacion.sustento s ON s.periodo_id = p.id AND s.car = d.car
         WHERE d.trabajo_id = p.trabajo_vigente_id AND {_PENDIENTE_SQL}) AS pendientes
  FROM comparacion.periodo p
  JOIN nucleo.empresa e ON e.id = p.empresa_id
  LEFT JOIN nucleo.trabajo tv ON tv.id = p.trabajo_vigente_id
"""


async def obtener_o_crear(conn: AsyncConnection, empresa_id: int, periodo: str) -> dict:
    await conn.execute(
        "INSERT INTO comparacion.periodo (empresa_id, periodo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (empresa_id, periodo),
    )
    return await obtener(conn, empresa_id, periodo)


async def obtener(conn: AsyncConnection, empresa_id: int, periodo: str) -> Optional[dict]:
    cur = await conn.execute(_SELECT_PERIODO + " WHERE p.empresa_id = %s AND p.periodo = %s", (empresa_id, periodo))
    return await cur.fetchone()


async def obtener_por_id(conn: AsyncConnection, periodo_id: int) -> Optional[dict]:
    cur = await conn.execute(_SELECT_PERIODO + " WHERE p.id = %s", (periodo_id,))
    return await cur.fetchone()


async def listar(conn: AsyncConnection, limite: int = 100) -> list[dict]:
    cur = await conn.execute(_SELECT_PERIODO + " ORDER BY p.periodo DESC, e.ruc LIMIT %s", (limite,))
    return await cur.fetchall()


async def registrar_carga(conn: AsyncConnection, empresa_id: int, periodo: str, trabajo_id: int) -> None:
    """La carga pasa a ser la vigente del periodo y se borra el detalle de las anteriores.
    Lo llama el worker dentro de la transacción que guarda el resultado."""
    cur = await conn.execute(
        "SELECT id, estado FROM comparacion.periodo WHERE empresa_id = %s AND periodo = %s FOR UPDATE",
        (empresa_id, periodo),
    )
    p = await cur.fetchone()
    if p is None:
        p = await obtener_o_crear(conn, empresa_id, periodo)
    elif p["estado"] == CERRADO:
        raise ValueError(f"El periodo {periodo} está cerrado; reábralo para volver a cargar")

    anteriores = """SELECT id FROM nucleo.trabajo
                     WHERE empresa_id = %s AND periodo = %s AND proceso_codigo = 'COMPARACION' AND id <> %s"""
    params = (empresa_id, periodo, trabajo_id)
    await conn.execute(f"DELETE FROM comparacion.detalle WHERE trabajo_id IN ({anteriores})", params)
    await conn.execute(f"DELETE FROM comparacion.totales WHERE trabajo_id IN ({anteriores})", params)
    await conn.execute(
        "UPDATE comparacion.periodo SET trabajo_vigente_id = %s, actualizado_en = now() WHERE id = %s",
        (trabajo_id, p["id"]),
    )
    await conn.execute(
        """INSERT INTO comparacion.periodo_evento (periodo_id, tipo, trabajo_id, usuario)
           SELECT %s, 'CARGA', id, usuario FROM nucleo.trabajo WHERE id = %s""",
        (p["id"], trabajo_id),
    )
    # Los rechazados por SUNAT que solo están en Bizlinks quedan sustentados solos (si nadie los tocó)
    cur = await conn.execute(
        """
        INSERT INTO comparacion.sustento (periodo_id, car, estado, motivo, comentario, usuario)
        SELECT %s, d.car, 'SUSTENTADO', %s, 'Automático: rechazado por SUNAT', 'sistema'
          FROM comparacion.detalle d
         WHERE d.trabajo_id = %s AND d.estado = 'SOLO_BIZLINKS' AND d.biz_estado LIKE '%%RC_05'
        ON CONFLICT (periodo_id, car) DO NOTHING
        RETURNING car
        """,
        (p["id"], MOTIVO_RECHAZADO, trabajo_id),
    )
    for fila in await cur.fetchall():
        await _historial(conn, p["id"], fila["car"], SUSTENTADO, MOTIVO_RECHAZADO,
                         "Automático: rechazado por SUNAT", "sistema", trabajo_id)


async def motivos(conn: AsyncConnection) -> list[dict]:
    cur = await conn.execute(
        "SELECT codigo, descripcion FROM comparacion.motivo_sustento WHERE activo ORDER BY orden, codigo"
    )
    return await cur.fetchall()


async def guardar_sustento(conn: AsyncConnection, periodo_id: int, car: str, estado: str, motivo: Optional[str],
                           comentario: Optional[str], usuario: Optional[str]) -> None:
    p = await obtener_por_id(conn, periodo_id)
    if p is None:
        raise ValueError("El periodo no existe")
    if p["estado"] == CERRADO:
        raise ValueError("El periodo está cerrado; reábralo para cambiar sustentos")
    if estado != PENDIENTE and not (motivo and (comentario or "").strip()):
        raise ValueError("Indique el motivo y el comentario")
    await conn.execute(
        """
        INSERT INTO comparacion.sustento (periodo_id, car, estado, motivo, comentario, usuario, actualizado_en)
        VALUES (%s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (periodo_id, car) DO UPDATE
           SET estado = EXCLUDED.estado, motivo = EXCLUDED.motivo, comentario = EXCLUDED.comentario,
               usuario = EXCLUDED.usuario, actualizado_en = now()
        """,
        (periodo_id, car, estado, motivo, comentario, usuario),
    )
    await _historial(conn, periodo_id, car, estado, motivo, comentario, usuario, p["trabajo_vigente_id"])


async def historial_sustento(conn: AsyncConnection, periodo_id: int, car: str) -> list[dict]:
    cur = await conn.execute(
        """SELECT estado, motivo, comentario, usuario, trabajo_id, creado_en FROM comparacion.sustento_historial
            WHERE periodo_id = %s AND car = %s ORDER BY creado_en DESC""",
        (periodo_id, car),
    )
    return await cur.fetchall()


async def cerrar(conn: AsyncConnection, periodo_id: int, usuario: Optional[str], comentario: Optional[str]) -> str:
    """Devuelve '' si se cerró, o el motivo por el que no se puede cerrar."""
    p = await obtener_por_id(conn, periodo_id)
    if p is None:
        return "El periodo no existe"
    if p["estado"] == CERRADO:
        return "El periodo ya está cerrado"
    if p["trabajo_vigente_id"] is None:
        return "El periodo no tiene una carga terminada"
    if p["pendientes"]:
        return f"Faltan sustentar {p['pendientes']} comprobantes (pendientes o en corrección)"
    await conn.execute(
        "UPDATE comparacion.periodo SET estado = 'CERRADO', cerrado_en = now(), cerrado_por = %s, "
        "actualizado_en = now() WHERE id = %s",
        (usuario, periodo_id),
    )
    await _evento(conn, periodo_id, "CIERRE", p["trabajo_vigente_id"], comentario, usuario)
    return ""


async def reabrir(conn: AsyncConnection, periodo_id: int, usuario: Optional[str], comentario: str) -> str:
    if not (comentario or "").strip():
        return "Indique por qué se reabre el periodo"
    cur = await conn.execute(
        "UPDATE comparacion.periodo SET estado = 'ABIERTO', cerrado_en = NULL, cerrado_por = NULL, "
        "actualizado_en = now() WHERE id = %s AND estado = 'CERRADO' RETURNING trabajo_vigente_id",
        (periodo_id,),
    )
    fila = await cur.fetchone()
    if fila is None:
        return "El periodo no está cerrado"
    await _evento(conn, periodo_id, "REAPERTURA", fila["trabajo_vigente_id"], comentario, usuario)
    return ""


async def eventos(conn: AsyncConnection, periodo_id: int) -> list[dict]:
    cur = await conn.execute(
        """SELECT tipo, trabajo_id, comentario, usuario, creado_en FROM comparacion.periodo_evento
            WHERE periodo_id = %s ORDER BY creado_en DESC, id DESC""",
        (periodo_id,),
    )
    return await cur.fetchall()


async def _evento(conn: AsyncConnection, periodo_id: int, tipo: str, trabajo_id: Optional[int],
                  comentario: Optional[str], usuario: Optional[str]) -> None:
    await conn.execute(
        "INSERT INTO comparacion.periodo_evento (periodo_id, tipo, trabajo_id, comentario, usuario) "
        "VALUES (%s, %s, %s, %s, %s)",
        (periodo_id, tipo, trabajo_id, comentario, usuario),
    )


async def _historial(conn: AsyncConnection, periodo_id: int, car: str, estado: str, motivo: Optional[str],
                     comentario: Optional[str], usuario: Optional[str], trabajo_id: Optional[int]) -> None:
    await conn.execute(
        "INSERT INTO comparacion.sustento_historial "
        "(periodo_id, car, estado, motivo, comentario, usuario, trabajo_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (periodo_id, car, estado, motivo, comentario, usuario, trabajo_id),
    )
