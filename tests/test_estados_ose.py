import unittest

from app.nucleo import estados_ose as e


class EstadosOseTest(unittest.TestCase):
    def test_categorias_del_catalogo(self):
        self.assertEqual(e.categoria("SIGNED/AC_03"), e.ACEPTADO)
        self.assertEqual(e.categoria("SIGNED/RC_05"), e.RECHAZADO)
        self.assertEqual(e.categoria("SIGNED/AN_04"), e.ANULADO)
        for pendiente in ("SIGNED", "SIGNED/PE_02", "SIGNED/PE_09", "SIGNED/ED_06"):
            self.assertEqual(e.categoria(pendiente), e.PENDIENTE, pendiente)

    def test_normaliza_espacios_y_mayusculas(self):
        self.assertEqual(e.normalizar("SIGNED/ AC_03 "), "SIGNED/AC_03")
        self.assertEqual(e.categoria("signed/ac_03"), e.ACEPTADO)

    def test_desconocido(self):
        self.assertEqual(e.categoria(None), e.DESCONOCIDO)
        self.assertEqual(e.categoria("SIGNED/XX_99"), e.DESCONOCIDO)
        self.assertEqual(e.descripcion("SIGNED/XX_99"), "SIGNED/XX_99")
        self.assertEqual(e.descripcion("SIGNED/AC_03"), "Aceptado por SUNAT")


if __name__ == "__main__":
    unittest.main()
