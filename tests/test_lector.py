import io
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from app.nucleo.sire.lector import leer_rvie

RUC = "20100000001"
EJEMPLO = (Path(__file__).parent / "datos" / "sire_rvie_ejemplo.txt").read_bytes()
# Mismo encabezado de 40 columnas que el CSV que exporta el SIRE (datos ficticios)
EXPORTADO = (Path(__file__).parent / "datos" / "sire_rvie_exportado.csv").read_bytes()


class LectorExportadoSireTest(unittest.TestCase):
    def setUp(self):
        self.lectura = leer_rvie(EXPORTADO, "LE2010000000120260900140400021112EXP2.csv", RUC, "202609")
        self.por_llave = {c.llave: c for c in self.lectura.comprobantes}

    def test_lee_todas_las_filas(self):
        self.assertEqual(self.lectura.errores, [])
        self.assertEqual(len(self.lectura.comprobantes), 4)

    def test_montos_sin_decimales(self):
        boleta = self.por_llave[RUC + "03B2020000064945"]
        self.assertEqual((boleta.base_imponible, boleta.igv, boleta.total),
                         (Decimal("860.00"), Decimal("154.80"), Decimal("1014.80")))
        self.assertEqual(boleta.doc_receptor, "40000001")

    def test_anulado(self):
        self.assertTrue(self.por_llave[RUC + "03B2020000064948"].anulado)
        self.assertFalse(self.por_llave[RUC + "03B2020000064945"].anulado)

    def test_nota_de_credito_con_importe_en_dscto(self):
        # El SIRE deja BI/IGV en cero y registra el importe en "Dscto BI" / "Dscto IGV / IPM"
        nc = self.por_llave[RUC + "07B1010000000754"]
        self.assertEqual((nc.base_imponible, nc.igv, nc.total),
                         (Decimal("-29.92"), Decimal("-5.39"), Decimal("-35.31")))

    def test_llave_es_el_car_sunat(self):
        self.assertIn("2010000000103B2020000064945", self.por_llave)

    def test_car_que_no_corresponde_a_la_fila_es_error(self):
        alterado = EXPORTADO.replace(b"2010000000103B2020000064945", b"2010000000103B2020000099999")
        lectura = leer_rvie(alterado, "x.csv", RUC, "202609")
        self.assertEqual(len(lectura.comprobantes), 3)
        self.assertIn("CAR SUNAT 2010000000103B2020000099999 no corresponde", lectura.errores[0])

    def test_periodo_distinto_es_error(self):
        lectura = leer_rvie(EXPORTADO, "x.csv", RUC, "202610")
        self.assertEqual(lectura.comprobantes, [])
        self.assertIn("periodo 202609", lectura.errores[0])


class LectorTest(unittest.TestCase):
    def test_txt_con_pipes(self):
        lectura = leer_rvie(EJEMPLO, "LE2010000000120260900140400021112.txt", RUC)
        self.assertEqual(lectura.errores, [])
        self.assertEqual(len(lectura.comprobantes), 6)
        primero = lectura.comprobantes[0]
        self.assertEqual(primero.llave, RUC + "01F0010000000001")
        self.assertEqual(primero.total, Decimal("118.00"))
        self.assertEqual(primero.moneda, "PEN")

    def test_zip_de_sunat(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("propuesta.txt", EJEMPLO)
        lectura = leer_rvie(buffer.getvalue(), "propuesta.zip", RUC)
        self.assertEqual(len(lectura.comprobantes), 6)

    def test_csv_latin1_con_comas(self):
        texto = "Tipo CP/Doc.,Serie del CDP,Nro CP o Doc. Nro Inicial (Rango),Total CP,Fecha de emisión\n1,f001,7,10.5,01/09/2026\n"
        lectura = leer_rvie(texto.encode("latin-1"), "ventas.csv", RUC)
        self.assertEqual(lectura.comprobantes[0].llave, RUC + "01F0010000000007")

    def test_xlsx(self):
        import openpyxl

        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.append(["RUC", "Tipo CP/Doc.", "Serie del CDP", "Nro CP o Doc. Nro Inicial (Rango)", "Total CP"])
        hoja.append([RUC, "01", "F001", 3, 354])
        buffer = io.BytesIO()
        libro.save(buffer)
        lectura = leer_rvie(buffer.getvalue(), "ventas.xlsx", RUC)
        self.assertEqual(lectura.comprobantes[0].total, Decimal("354.00"))

    def test_fila_invalida_se_reporta_sin_detener_la_lectura(self):
        texto = "Tipo CP/Doc.|Serie del CDP|Nro CP o Doc. Nro Inicial (Rango)\n01|F001|1\n01|F001|ABC\n"
        lectura = leer_rvie(texto.encode(), "x.txt", RUC)
        self.assertEqual(len(lectura.comprobantes), 1)
        self.assertEqual(len(lectura.errores), 1)
        self.assertIn("Fila 3", lectura.errores[0])

    def test_ruc_de_otra_empresa_es_error(self):
        lectura = leer_rvie(EJEMPLO, "x.txt", "20999999999")
        self.assertEqual(lectura.comprobantes, [])
        self.assertEqual(len(lectura.errores), 6)

    def test_faltan_columnas_obligatorias(self):
        with self.assertRaises(ValueError):
            leer_rvie(b"Columna A|Columna B\n1|2\n", "x.txt", RUC)

    def test_extension_no_soportada(self):
        with self.assertRaises(ValueError):
            leer_rvie(b"", "x.pdf", RUC)


if __name__ == "__main__":
    unittest.main()
