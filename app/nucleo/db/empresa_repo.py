"""Empresas (RUC emisores) registradas."""

from typing import Optional

from psycopg import AsyncConnection


async def listar(conn: AsyncConnection, solo_activas: bool = False) -> list[dict]:
    sql = "SELECT id, ruc, razon_social, activo FROM nucleo.empresa"
    if solo_activas:
        sql += " WHERE activo"
    cur = await conn.execute(sql + " ORDER BY razon_social")
    return await cur.fetchall()


async def obtener(conn: AsyncConnection, empresa_id: int) -> Optional[dict]:
    cur = await conn.execute(
        "SELECT id, ruc, razon_social, activo FROM nucleo.empresa WHERE id = %s", (empresa_id,)
    )
    return await cur.fetchone()


async def crear(conn: AsyncConnection, ruc: str, razon_social: str) -> int:
    cur = await conn.execute(
        "INSERT INTO nucleo.empresa (ruc, razon_social) VALUES (%s, %s) RETURNING id",
        (ruc, razon_social),
    )
    return (await cur.fetchone())["id"]


async def cambiar_activo(conn: AsyncConnection, empresa_id: int, activo: bool) -> None:
    await conn.execute(
        "UPDATE nucleo.empresa SET activo = %s WHERE id = %s", (activo, empresa_id)
    )
