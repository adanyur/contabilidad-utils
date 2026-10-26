"""Worker de segundo plano: lee las colas pgmq de los procesos registrados y ejecuta sus manejadores.

    python -m app.worker

Se pueden levantar varios (docker compose up --scale worker=N): pgmq garantiza que cada
mensaje lo toma un solo worker. Si un worker se cae, el mensaje reaparece al vencer el vt.
"""

import asyncio
import logging
import signal
import socket
import sys

from app import config
from app.nucleo.db import cola_repo, conexion
from app.procesos import REGISTRO
from app.procesos.base import Proceso

log = logging.getLogger("worker")


class _Contexto:
    def __init__(self, trabajo_id: int):
        self.trabajo_id = trabajo_id

    async def avance(self, progreso: int, mensaje: str) -> None:
        pool = await conexion.historial()
        async with pool.connection() as conn:
            await cola_repo.avance(conn, self.trabajo_id, progreso, mensaje)


class Worker:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.id = socket.gethostname()
        self.parar = asyncio.Event()

    async def correr(self) -> None:
        procesos = list(REGISTRO.values())
        # Con varias colas se reparte la espera para no quedarse bloqueado en una sola
        espera = max(1, 5 // len(procesos))
        log.info("Worker %s escuchando: %s", self.id, ", ".join(p.cola for p in procesos))
        while not self.parar.is_set():
            for proceso in procesos:
                if self.parar.is_set():
                    break
                try:
                    await self._atender(proceso, espera)
                except Exception:
                    log.exception("Error leyendo la cola %s", proceso.cola)
                    await asyncio.sleep(5)
        log.info("Worker %s detenido", self.id)

    async def _atender(self, proceso: Proceso, espera: int) -> None:
        pool = await conexion.historial()
        async with pool.connection() as conn:
            msg = await cola_repo.leer(conn, proceso.cola, self.cfg.worker_vt, espera)
        if msg is not None:
            await self._procesar(proceso, msg)

    async def _procesar(self, proceso: Proceso, msg: cola_repo.Mensaje) -> None:
        pool = await conexion.historial()
        async with pool.connection() as conn:
            trabajo = await cola_repo.obtener(conn, msg.trabajo_id)
            if trabajo is None or trabajo.estado in ("OK", "CANCELADO", "ERROR"):
                # Trabajo cancelado, ya terminado o mensaje duplicado
                await cola_repo.archivar(conn, proceso.cola, msg.msg_id)
                return
            if msg.read_ct > trabajo.max_intentos:
                await cola_repo.finalizar(conn, trabajo.id, "ERROR", "Se superó el número máximo de intentos")
                await cola_repo.archivar(conn, proceso.cola, msg.msg_id)
                return
            await cola_repo.marcar_en_proceso(conn, trabajo.id, msg.msg_id, msg.read_ct, self.id)

        log.info("Trabajo %s (%s) intento %s", trabajo.id, proceso.codigo, msg.read_ct)
        mantener = asyncio.create_task(self._mantener_vivo(proceso.cola, msg.msg_id, trabajo.id))
        try:
            mensaje = await proceso.manejador(trabajo, _Contexto(trabajo.id))
        except Exception as e:
            log.exception("Trabajo %s falló", trabajo.id)
            async with pool.connection() as conn:
                if msg.read_ct >= trabajo.max_intentos:
                    await cola_repo.finalizar(conn, trabajo.id, "ERROR", str(e))
                    await cola_repo.archivar(conn, proceso.cola, msg.msg_id)
                else:
                    # Se deja el mensaje: reaparece al vencer el vt y se reintenta
                    await cola_repo.finalizar(conn, trabajo.id, "PENDIENTE", f"Error, se reintentará: {e}")
                    await cola_repo.extender(conn, proceso.cola, msg.msg_id, 10)
        else:
            async with pool.connection() as conn:
                await cola_repo.finalizar(conn, trabajo.id, "OK", mensaje)
                await cola_repo.archivar(conn, proceso.cola, msg.msg_id)
            log.info("Trabajo %s OK: %s", trabajo.id, mensaje)
        finally:
            mantener.cancel()

    async def _mantener_vivo(self, cola: str, msg_id: int, trabajo_id: int) -> None:
        """Extiende el vt y marca el latido mientras el manejador sigue trabajando."""
        intervalo = max(5, self.cfg.worker_vt // 2)
        pool = await conexion.historial()
        while True:
            await asyncio.sleep(intervalo)
            try:
                async with pool.connection() as conn:
                    await cola_repo.extender(conn, cola, msg_id, self.cfg.worker_vt)
                    await cola_repo.latido(conn, trabajo_id)
            except Exception:
                log.exception("No se pudo extender el vt del mensaje %s", msg_id)


async def main() -> None:
    cfg = config.cargar()
    config.configurar_logging(cfg)
    worker = Worker(cfg)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            # Termina el trabajo en curso y luego sale
            loop.add_signal_handler(sig, worker.parar.set)
        except NotImplementedError:  # Windows
            pass
    try:
        await worker.correr()
    finally:
        await conexion.cerrar()


if __name__ == "__main__":
    # psycopg async no funciona con el ProactorEventLoop de Windows (solo aplica fuera de Docker)
    fabrica = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=fabrica)
