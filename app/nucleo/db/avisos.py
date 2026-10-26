"""Escucha LISTEN trabajo_avance una sola vez por proceso web y despierta a las vistas que esperan.

Las vistas llaman a esperar(timeout): vuelve al llegar un aviso o al vencer el timeout,
así que la consulta periódica de respaldo sale gratis.
"""

import asyncio
import logging

import psycopg

from app import config
from app.nucleo.db.cola_repo import CANAL_AVANCE

log = logging.getLogger(__name__)

_condicion: asyncio.Condition | None = None
_tarea: asyncio.Task | None = None


def iniciar() -> None:
    global _condicion, _tarea
    if _tarea is None or _tarea.done():
        _condicion = asyncio.Condition()
        _tarea = asyncio.get_running_loop().create_task(_escuchar())


async def esperar(timeout: float) -> None:
    if _condicion is None:
        await asyncio.sleep(timeout)
        return
    async with _condicion:
        try:
            await asyncio.wait_for(_condicion.wait(), timeout)
        except TimeoutError:
            pass


async def _escuchar() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(config.cargar().hist_dsn, autocommit=True) as conn:
                await conn.execute(f"LISTEN {CANAL_AVANCE}")
                log.info("Escuchando %s", CANAL_AVANCE)
                async for _ in conn.notifies():
                    async with _condicion:
                        _condicion.notify_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Se perdió la conexión LISTEN; reintentando en 5 s")
            await asyncio.sleep(5)
