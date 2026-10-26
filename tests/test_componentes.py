import unittest
from datetime import date

from app.nucleo.ui import componentes as c


class PeriodosTest(unittest.TestCase):
    def test_empieza_en_el_mes_en_curso(self):
        self.assertEqual(c.periodos(3, date(2026, 10, 25)), ["202610", "202609", "202608"])

    def test_cruza_el_cambio_de_anio(self):
        self.assertEqual(c.periodos(3, date(2026, 2, 1)), ["202602", "202601", "202512"])


class SelectorEmpresaTest(unittest.TestCase):
    def test_una_sola_empresa_queda_seleccionada(self):
        self.assertEqual(c.selector_empresa([{"id": 7, "ruc": "20100375061", "razon_social": "X"}]).value, "7")

    def test_varias_empresas_no_seleccionan(self):
        empresas = [{"id": i, "ruc": str(i), "razon_social": "X"} for i in (1, 2)]
        self.assertIsNone(c.selector_empresa(empresas).value)


if __name__ == "__main__":
    unittest.main()
