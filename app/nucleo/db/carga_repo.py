"""Archivos cargados por los usuarios. El contenido se guarda en la BD para que el worker
no dependa de rutas locales."""

import hashlib
from typing import Optional

from psycopg import AsyncConnection


def calcular_hash(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


async def insertar(
    conn: AsyncConnection,
    empresa_id: int,
    periodo: str,
    tipo_origen: str,
    nombre_archivo: str,
    contenido: bytes,
    usuario: Optional[str],
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO nucleo.carga_archivo
            (empresa_id, periodo, tipo_origen, nombre_archivo, contenido, hash_archivo, tamano_bytes, usuario)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (empresa_id, periodo, tipo_origen, nombre_archivo, contenido,
         calcular_hash(contenido), len(contenido), usuario),
    )
    return (await cur.fetchone())["id"]


async def obtener(conn: AsyncConnection, carga_id: int) -> Optional[dict]:
    cur = await conn.execute(
        "SELECT id, empresa_id, periodo, nombre_archivo, contenido FROM nucleo.carga_archivo WHERE id = %s",
        (carga_id,),
    )
    return await cur.fetchone()


async def trabajo_previo_ok(
    conn: AsyncConnection, empresa_id: int, periodo: str, hash_archivo: str
) -> Optional[int]:
    """Id del último trabajo terminado con el mismo archivo, para avisar de recargas."""
    cur = await conn.execute(
        """
        SELECT t.id
          FROM nucleo.carga_archivo c
          JOIN nucleo.trabajo t ON t.carga_archivo_id = c.id
         WHERE c.empresa_id = %s AND c.periodo = %s AND c.hash_archivo = %s AND t.estado = 'OK'
         ORDER BY t.id DESC
         LIMIT 1
        """,
        (empresa_id, periodo, hash_archivo),
    )
    fila = await cur.fetchone()
    return fila["id"] if fila else None
