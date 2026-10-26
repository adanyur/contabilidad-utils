import unittest
from datetime import date
from decimal import Decimal

from app.nucleo.sire import normalizador as n


class NormalizadorTest(unittest.TestCase):
    def test_tipo_cp_rellena_a_dos_digitos(self):
        self.assertEqual(n.tipo_cp("1"), "01")
        self.assertEqual(n.tipo_cp(" 07 "), "07")

    def test_numero_sin_ceros_a_la_izquierda(self):
        self.assertEqual(n.numero("00000123"), 123)
        self.assertEqual(n.numero(123.0), 123)

    def test_serie_en_mayusculas(self):
        self.assertEqual(n.serie(" f001 "), "F001")

    def test_monto_decimal_exacto(self):
        self.assertEqual(n.monto("1,234.5"), Decimal("1234.50"))
        self.assertEqual(n.monto(""), Decimal("0.00"))
        self.assertEqual(n.monto(0.1), Decimal("0.10"))

    def test_fecha_formatos(self):
        self.assertEqual(n.fecha("01/09/2026"), date(2026, 9, 1))
        self.assertEqual(n.fecha("2026-09-01"), date(2026, 9, 1))
        self.assertIsNone(n.fecha(""))

    def test_valores_invalidos(self):
        with self.assertRaises(ValueError):
            n.ruc("123")
        with self.assertRaises(ValueError):
            n.numero("12A")
        with self.assertRaises(ValueError):
            n.monto("abc")

    def test_nombre_columna(self):
        self.assertEqual(n.nombre_columna("Fecha de emisión"), "fechadeemision")
        self.assertEqual(n.nombre_columna("IGV / IPM"), "igvipm")


if __name__ == "__main__":
    unittest.main()
