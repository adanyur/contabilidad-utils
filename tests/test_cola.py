"""Pruebas de integración de la cola pgmq contra la BD de historial (HIST_DSN).

Usan una cola y un proceso propios (prueba_cola / PRUEBA_COLA) que crean y borran, así no tocan
la cola real "comparacion" ni los trabajos de la BD compartida. Se activan explícitamente:

    docker compose run --rm -e PRUEBAS_BD=1 web python -m unittest tests.test_cola
"""

import os
import random
import unittest

from app.nucleo.db import cola_repo, conexion, empresa_repo

COLA = "prueba_cola"
PROCESO = "PRUEBA_COLA"


@unittest.skipUnless(os.environ.get("PRUEBAS_BD") == "1", "requiere PRUEBAS_BD=1 y HIST_DSN")
class ColaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = await conexion.historial()
        async with self.pool.connection() as conn:
            await conn.execute("SELECT pgmq.create(%s)", (COLA,))
            await conn.execute(
                "INSERT INTO nucleo.proceso (codigo, nombre, cola, activo) VALUES (%s, 'Prueba de cola', %s, false)"
                " ON CONFLICT (codigo) DO NOTHING",
                (PROCESO, COLA),
            )
            ruc = "209" + "".join(random.choices("0123456789", k=8))
            self.empresa_id = await empresa_repo.crear(conn, ruc, "EMPRESA PRUEBA COLA")

    async def asyncTearDown(self):
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM nucleo.trabajo WHERE empresa_id = %s", (self.empresa_id,))
            await conn.execute("DELETE FROM nucleo.empresa WHERE id = %s", (self.empresa_id,))
            await conn.execute("DELETE FROM nucleo.proceso WHERE codigo = %s", (PROCESO,))
            await conn.execute("SELECT pgmq.drop_queue(%s)", (COLA,))
        await conexion.cerrar()

    async def _encolar(self) -> int:
        async with self.pool.connection() as conn:
            return await cola_repo.encolar(conn, PROCESO, self.empresa_id, "202609", None, {}, 3, "test")

    async def _leer(self, vt=30):
        async with self.pool.connection() as conn:
            return await cola_repo.leer(conn, COLA, vt, 1)

    async def test_un_mensaje_lo_toma_un_solo_lector(self):
        trabajo_id = await self._encolar()
        primero = await self._leer()
        segundo = await self._leer()
        self.assertEqual(primero.trabajo_id, trabajo_id)
        self.assertIsNone(segundo)

    async def test_mensaje_no_archivado_reaparece_al_vencer_el_vt(self):
        await self._encolar()
        msg = await self._leer()
        async with self.pool.connection() as conn:
            await cola_repo.extender(conn, COLA, msg.msg_id, 0)  # simula que venció el vt
        otra_vez = await self._leer()
        self.assertEqual(otra_vez.msg_id, msg.msg_id)
        self.assertEqual(otra_vez.read_ct, 2)

    async def test_archivar_y_finalizar(self):
        trabajo_id = await self._encolar()
        msg = await self._leer()
        async with self.pool.connection() as conn:
            await cola_repo.finalizar(conn, trabajo_id, "OK", "listo")
            await cola_repo.archivar(conn, COLA, msg.msg_id)
            trabajo = await cola_repo.obtener(conn, trabajo_id)
        self.assertEqual((trabajo.estado, trabajo.progreso), ("OK", 100))
        self.assertIsNone(await self._leer())

    async def test_cancelar_solo_pendientes_y_reintentar(self):
        trabajo_id = await self._encolar()
        async with self.pool.connection() as conn:
            self.assertTrue(await cola_repo.cancelar(conn, trabajo_id))
            self.assertFalse(await cola_repo.cancelar(conn, trabajo_id))
            self.assertTrue(await cola_repo.reintentar(conn, trabajo_id))
            trabajo = await cola_repo.obtener(conn, trabajo_id)
        self.assertEqual(trabajo.estado, "PENDIENTE")


if __name__ == "__main__":
    unittest.main()
