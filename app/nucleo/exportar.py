"""Exporta filas a CSV (librería estándar) o XLSX (openpyxl)."""

import csv
import io
from typing import Iterable, Sequence


def a_csv(columnas: Sequence[str], filas: Iterable[Sequence]) -> bytes:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(columnas)
    escritor.writerows(["" if v is None else v for v in fila] for fila in filas)
    # utf-8-sig para que Excel reconozca las tildes al abrir el CSV
    return salida.getvalue().encode("utf-8-sig")


def a_xlsx(columnas: Sequence[str], filas: Iterable[Sequence], hoja: str = "Resultado") -> bytes:
    import openpyxl  # solo se necesita para Excel

    libro = openpyxl.Workbook(write_only=True)
    ws = libro.create_sheet(hoja)
    ws.append(list(columnas))
    for fila in filas:
        ws.append(list(fila))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
