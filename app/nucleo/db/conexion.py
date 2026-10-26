"""Pools asíncronos de conexión: uno para la BD de historial y otro (solo lectura) para Bizlinks.

Los pools se abren la primera vez que se piden y quedan ligados al event loop del proceso
(el de Flet en la web, el de asyncio.run en el worker).
"""

import asyncio

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app import config

_pools: dict[str, AsyncConnectionPool] = {}
_candado = asyncio.Lock()


async def _pool(nombre: str, dsn: str, **kwargs) -> AsyncConnectionPool:
    pool = _pools.get(nombre)
    if pool is not None:
        return pool
    async with _candado:
        if nombre not in _pools:
            pool = AsyncConnectionPool(
                dsn,
                min_size=1,
                max_size=10,
                open=False,
                name=nombre,
                kwargs={"row_factory": dict_row, **kwargs},
            )
            await pool.open(wait=True, timeout=30)
            _pools[nombre] = pool
    return _pools[nombre]


async def historial() -> AsyncConnectionPool:
    return await _pool("historial", config.cargar().hist_dsn)


async def bizlinks() -> AsyncConnectionPool:
    # Toda transacción en Bizlinks es de solo lectura, aunque el usuario tuviera más permisos
    return await _pool(
        "bizlinks",
        config.cargar().bizlinks_dsn,
        options="-c default_transaction_read_only=on",
    )


async def cerrar() -> None:
    while _pools:
        _, pool = _pools.popitem()
        await pool.close()
