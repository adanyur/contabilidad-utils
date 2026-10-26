import unittest
from datetime import date
from decimal import Decimal

from app.nucleo.modelos import Comprobante
from app.procesos.comparacion import motor

RUC = "20100000001"
TOL = Decimal("0.01")


def cp(numero, total="118.00", serie="F001", tipo="01", fecha=date(2026, 9, 1), moneda="PEN"):
    total = Decimal(total)
    return Comprobante(RUC, tipo, serie, numero, fecha, moneda, total, Decimal("0"), total)


class MotorTest(unittest.TestCase):
    def test_cuatro_estados(self):
        sire = [cp(1), cp(2, "100.00"), cp(3)]
        biz = [cp(1), cp(2, "90.00"), cp(4)]
        r = motor.comparar(sire, biz, TOL)
        estados = {(d.sire or d.bizlinks).numero: d.estado for d in r.detalles}
        self.assertEqual(estados, {1: "COINCIDE", 2: "DIFERENCIA", 3: "SOLO_SIRE", 4: "SOLO_BIZLINKS"})
        self.assertEqual(r.resumen["COINCIDE"], 1)
        self.assertEqual((r.total_sire, r.total_bizlinks), (3, 3))

    def test_tolerancia(self):
        r = motor.comparar([cp(1, "100.00")], [cp(1, "100.01")], TOL)
        self.assertEqual(r.detalles[0].estado, "COINCIDE")
        r = motor.comparar([cp(1, "100.00")], [cp(1, "100.02")], TOL)
        self.assertEqual(r.detalles[0].estado, "DIFERENCIA")
        self.assertEqual(r.detalles[0].diferencias["total"], {"sire": "100.00", "bizlinks": "100.02"})

    def test_nota_de_credito_negativa_en_sire(self):
        r = motor.comparar([cp(1, "-11.80", tipo="07")], [cp(1, "11.80", tipo="07")], TOL)
        self.assertEqual(r.detalles[0].estado, "COINCIDE")

    def test_anulado_en_ambos_coincide_y_en_uno_solo_es_diferencia(self):
        anulado_sire = Comprobante(RUC, "01", "F001", 1, date(2026, 9, 1), "PEN", anulado=True)
        anulado_biz = cp(1, "426.52")
        r = motor.comparar([anulado_sire], [Comprobante(**{**anulado_biz.__dict__, "anulado": True})], TOL)
        self.assertEqual(r.detalles[0].estado, "COINCIDE")
        r = motor.comparar([cp(1, "426.52")], [Comprobante(**{**anulado_biz.__dict__, "anulado": True})], TOL)
        self.assertEqual(r.detalles[0].estado, "DIFERENCIA")
        self.assertEqual(r.detalles[0].diferencias["anulado"], {"sire": "NO", "bizlinks": "SI"})

    def test_rechazado_en_bizlinks(self):
        rechazado = Comprobante(RUC, "01", "F001", 9, date(2026, 9, 1), "PEN", Decimal("100"), Decimal("18"),
                                Decimal("118"), estado_ose="SIGNED/RC_05")
        r = motor.comparar([], [rechazado], TOL)
        self.assertEqual((r.detalles[0].estado, r.solo_bizlinks_rechazados), ("SOLO_BIZLINKS", 1))
        # Si a pesar del rechazo figura en el SIRE, es una diferencia
        r = motor.comparar([cp(9)], [rechazado], TOL)
        self.assertEqual(r.detalles[0].estado, "DIFERENCIA")
        self.assertIn("estado_ose", r.detalles[0].diferencias)

    def test_pendientes_en_bizlinks(self):
        pendiente = Comprobante(RUC, "03", "B001", 9, date(2026, 9, 30), "PEN", estado_ose="SIGNED/PE_09")
        r = motor.comparar([], [pendiente], TOL)
        self.assertEqual((r.solo_bizlinks_pendientes, r.solo_bizlinks_rechazados), (1, 0))

    def test_fecha_y_moneda(self):
        r = motor.comparar([cp(1)], [cp(1, fecha=date(2026, 9, 2), moneda="USD")], TOL)
        self.assertEqual(set(r.detalles[0].diferencias), {"fecha_emision", "moneda"})

    def test_duplicados_se_reportan(self):
        r = motor.comparar([cp(1), cp(1)], [cp(1)], TOL)
        self.assertEqual(r.duplicados_sire, [RUC + "01F0010000000001"])
        self.assertEqual(len(r.detalles), 1)

    def test_llave_distingue_serie_y_tipo(self):
        r = motor.comparar([cp(1, serie="F001")], [cp(1, serie="F002")], TOL)
        self.assertEqual(sorted(d.estado for d in r.detalles), ["SOLO_BIZLINKS", "SOLO_SIRE"])


if __name__ == "__main__":
    unittest.main()
