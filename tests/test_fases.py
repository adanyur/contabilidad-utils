import unittest
from datetime import date
from decimal import Decimal

from app.nucleo.modelos import Comprobante
from app.procesos.comparacion import igv, motor, totales

RUC = "20100000001"
TASA = Decimal("0.18")
TOL = Decimal("0.01")


def cp(numero, base, igv_, tipo="01", serie="F001", anulado=False, estado_ose=None, signo=1):
    base, igv_ = Decimal(base) * signo, Decimal(igv_) * signo
    return Comprobante(RUC, tipo, serie, numero, date(2026, 9, 1), "PEN", base, igv_, base + igv_,
                       anulado=anulado, estado_ose=estado_ose)


class TotalesTest(unittest.TestCase):
    def test_suma_por_tipo_y_total_con_notas_de_credito_restando(self):
        sire = [cp(1, "100", "18"), cp(2, "200", "36"), cp(1, "50", "9", tipo="07", serie="FC01", signo=-1)]
        biz = [cp(1, "100", "18"), cp(2, "200", "36"), cp(1, "50", "9", tipo="07", serie="FC01")]
        r = totales.calcular(sire, biz, TASA)
        filas = {f.tipo_cp: f for f in r.filas}
        self.assertEqual([f.tipo_cp for f in r.filas], ["01", "07", "TOTAL"])
        self.assertEqual((filas["TOTAL"].sire.cantidad, filas["TOTAL"].sire.base), (3, Decimal("250")))
        self.assertEqual(filas["TOTAL"].bizlinks.total, Decimal("295"))
        self.assertEqual(filas["TOTAL"].diferencias(TOL), {})

    def test_excluye_anulados_y_rechazados(self):
        sire = [cp(1, "100", "18"), cp(2, "0", "0", anulado=True)]
        biz = [cp(1, "100", "18"), cp(2, "300", "54", anulado=True), cp(3, "10", "1.8", estado_ose="SIGNED/RC_05")]
        r = totales.calcular(sire, biz, TASA)
        self.assertEqual((r.excluidos_sire, r.excluidos_bizlinks), (1, 2))
        self.assertEqual(r.filas[-1].diferencias(TOL), {})

    def test_diferencia_en_totales(self):
        r = totales.calcular([cp(1, "100", "18")], [cp(1, "100", "18"), cp(2, "10", "1.80")], TASA)
        dif = r.filas[-1].diferencias(TOL)
        self.assertEqual(dif["cantidad"], {"sire": "1", "bizlinks": "2"})
        self.assertEqual(dif["total"], {"sire": "118", "bizlinks": "129.80"})


class IgvTest(unittest.TestCase):
    def test_calcula_redondeando_y_en_valor_absoluto(self):
        self.assertEqual(igv.calcular(Decimal("29.92"), TASA), Decimal("5.39"))
        self.assertEqual(igv.calcular(Decimal("-29.92"), TASA), Decimal("5.39"))

    def test_observa_solo_el_lado_que_se_aparta(self):
        r = motor.comparar([cp(1, "342.35", "0.01")], [cp(1, "342.35", "61.62")], TOL)
        v = igv.verificar(r.detalles, TASA, Decimal("0.05"))[r.detalles[0].llave]
        self.assertEqual((v.sire_calculado, v.sire_observado, v.biz_observado), (Decimal("61.62"), True, False))

    def test_tolerancia_por_redondeo_de_lineas(self):
        r = motor.comparar([cp(1, "100", "18.04")], [], TOL)
        self.assertFalse(igv.verificar(r.detalles, TASA, Decimal("0.05"))[r.detalles[0].llave].observado)
        self.assertTrue(igv.verificar(r.detalles, TASA, Decimal("0.01"))[r.detalles[0].llave].observado)

    def test_anulado_no_se_verifica(self):
        r = motor.comparar([cp(1, "0", "0", anulado=True)], [], TOL)
        v = igv.verificar(r.detalles, TASA, TOL)[r.detalles[0].llave]
        self.assertEqual((v.sire_calculado, v.observado), (None, False))


if __name__ == "__main__":
    unittest.main()
