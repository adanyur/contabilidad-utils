"""Cabecera de periodo, recarga, sustento y cierre contra la BD de historial (HIST_DSN).

Todo corre dentro de una transacción que se deshace al final: no deja datos en la BD compartida.

    docker compose run --rm -e PRUEBAS_BD=1 web python -m unittest tests.test_periodo
"""

import os
import random
import unittest
from datetime import date
from decimal import Decimal

import psycopg

from app.nucleo.db import conexion, empresa_repo
from app.nucleo.modelos import Comprobante
from app.procesos.comparacion import igv, motor, periodo_repo, sustento

PERIODO = "202609"


class _Deshacer(Exception):
    pass


def cp(numero, total="118.00"):
    total = Decimal(total)
    return Comprobante("20100000001", "01", "F001", numero, date(2026, 9, 1), "PEN", total, Decimal("0"), total)


class RequiereSustentoTest(unittest.TestCase):
    def test_casos(self):
        rechazado = Comprobante("20100000001", "01", "F001", 4, estado_ose="SIGNED/RC_05")
        r = motor.comparar([cp(1), cp(2, "100"), cp(3)], [cp(1), cp(2, "90"), rechazado, cp(5)], Decimal("0.01"))
        v = igv.verificar(r.detalles, Decimal("0.18"), Decimal("0.05"))
        requiere = {(d.sire or d.bizlinks).numero: sustento.requiere(d, v[d.llave]) for d in r.detalles}
        # 1 coincide pero su IGV (0) no es base x 18%: también requiere sustento
        self.assertEqual(requiere, {1: True, 2: True, 3: True, 4: False, 5: True})


@unittest.skipUnless(os.environ.get("PRUEBAS_BD") == "1", "requiere PRUEBAS_BD=1 y HIST_DSN")
class PeriodoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await conexion.cerrar()

    async def _trabajo(self, conn, empresa_id: int) -> int:
        cur = await conn.execute(
            "INSERT INTO nucleo.trabajo (proceso_codigo, empresa_id, periodo, estado, usuario) "
            "VALUES ('COMPARACION', %s, %s, 'OK', 'prueba') RETURNING id",
            (empresa_id, PERIODO),
        )
        return (await cur.fetchone())["id"]

    async def _detalle(self, conn, trabajo_id: int, car: str, estado: str, requiere: bool, biz_estado=None):
        await conn.execute(
            "INSERT INTO comparacion.detalle (trabajo_id, car, tipo_cp, serie, numero, estado, requiere_sustento, "
            "biz_estado) VALUES (%s, %s, '01', 'F001', %s, %s, %s, %s)",
            (trabajo_id, car, int(car[-10:]), estado, requiere, biz_estado),
        )

    async def test_recarga_conserva_sustento_y_cierre(self):
        pool = await conexion.historial()
        with self.assertRaises(_Deshacer):
            async with pool.connection() as conn:
                async with conn.transaction():
                    await self._flujo(conn)
                    raise _Deshacer

    async def _flujo(self, conn):
        ruc = "208" + "".join(random.choices("0123456789", k=8))
        empresa_id = await empresa_repo.crear(conn, ruc, "EMPRESA PRUEBA PERIODO")
        car_dif, car_rech = f"{ruc}01F0010000000001", f"{ruc}01F0010000000002"

        # Primera carga: un comprobante con diferencia y un rechazado solo en Bizlinks
        t1 = await self._trabajo(conn, empresa_id)
        await self._detalle(conn, t1, car_dif, "DIFERENCIA", True)
        await self._detalle(conn, t1, car_rech, "SOLO_BIZLINKS", False, "SIGNED/RC_05")
        await periodo_repo.registrar_carga(conn, empresa_id, PERIODO, t1)
        p = await periodo_repo.obtener(conn, empresa_id, PERIODO)
        self.assertEqual((p["trabajo_vigente_id"], p["requieren_sustento"], p["pendientes"]), (t1, 1, 1))
        self.assertIn("Faltan sustentar 1", await periodo_repo.cerrar(conn, p["id"], "prueba", None))

        # En corrección todavía impide cerrar; sustentado sí permite
        await periodo_repo.guardar_sustento(conn, p["id"], car_dif, "EN_CORRECCION", "ERROR_SIRE", "Se rectifica", "prueba")
        self.assertEqual((await periodo_repo.obtener_por_id(conn, p["id"]))["pendientes"], 1)
        with self.assertRaises(ValueError):
            await periodo_repo.guardar_sustento(conn, p["id"], car_dif, "SUSTENTADO", None, "", "prueba")

        # Segunda carga: reemplaza el detalle y el sustento se conserva por CAR
        t2 = await self._trabajo(conn, empresa_id)
        await self._detalle(conn, t2, car_dif, "DIFERENCIA", True)
        await periodo_repo.registrar_carga(conn, empresa_id, PERIODO, t2)
        cur = await conn.execute("SELECT count(*) AS n FROM comparacion.detalle WHERE trabajo_id = %s", (t1,))
        self.assertEqual((await cur.fetchone())["n"], 0)
        cur = await conn.execute(
            "SELECT estado FROM comparacion.sustento WHERE periodo_id = %s AND car = %s", (p["id"], car_dif))
        self.assertEqual((await cur.fetchone())["estado"], "EN_CORRECCION")
        cur = await conn.execute(
            "SELECT motivo FROM comparacion.sustento WHERE periodo_id = %s AND car = %s", (p["id"], car_rech))
        self.assertEqual((await cur.fetchone())["motivo"], periodo_repo.MOTIVO_RECHAZADO)

        await periodo_repo.guardar_sustento(conn, p["id"], car_dif, "SUSTENTADO", "ERROR_SIRE", "Rectificado", "prueba")
        self.assertEqual(await periodo_repo.cerrar(conn, p["id"], "prueba", "Conciliado"), "")

        # Cerrado: no admite cargas ni cambios de sustento hasta reabrir (con motivo)
        t3 = await self._trabajo(conn, empresa_id)
        with self.assertRaises(ValueError):
            await periodo_repo.registrar_carga(conn, empresa_id, PERIODO, t3)
        with self.assertRaises(ValueError):
            await periodo_repo.guardar_sustento(conn, p["id"], car_dif, "PENDIENTE", None, None, "prueba")
        self.assertNotEqual(await periodo_repo.reabrir(conn, p["id"], "prueba", ""), "")
        self.assertEqual(await periodo_repo.reabrir(conn, p["id"], "prueba", "Llegó una rectificación"), "")
        tipos = [e["tipo"] for e in await periodo_repo.eventos(conn, p["id"])]
        self.assertEqual(tipos, ["REAPERTURA", "CIERRE", "CARGA", "CARGA"])


if __name__ == "__main__":
    unittest.main()
