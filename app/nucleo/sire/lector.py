"""Lee el registro de ventas (RVIE) exportado del SIRE: CSV o TXT, ZIP de SUNAT o XLSX.

Las columnas se ubican por el nombre del encabezado (sin tildes ni espacios), así que el orden
del archivo no importa. Si SUNAT cambia un encabezado, basta con agregar el alias en COLUMNAS.
"""

import csv
import io
import zipfile
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

from app.nucleo.modelos import Comprobante, armar_car
from app.nucleo.sire import normalizador as n

# campo -> encabezados aceptados (ya normalizados con n.nombre_columna)
COLUMNAS: dict[str, tuple[str, ...]] = {
    "ruc": ("ruc",),
    "periodo": ("periodo",),
    "car": ("carsunat", "car"),
    "estado": ("estcomp", "estadocomprobante"),
    "fecha_emision": ("fechadeemision", "fechaemision"),
    "tipo_cp": ("tipocpdoc", "tipocp", "tipodecomprobante", "tipocomprobante"),
    "serie": ("seriedelcdp", "seriecdp", "serie"),
    "numero": ("nrocpodocnroinicialrango", "nrocpodocnroinicial", "nrocp", "numero"),
    "doc_receptor": ("nrodocidentidad", "nrodocumentoidentidad"),
    "base_imponible": ("bigravada", "baseimponible"),
    "igv": ("igvipm", "igv"),
    # Las notas de crédito pueden venir con BI/IGV en cero y el importe en estas columnas
    "dscto_bi": ("dsctobi",),
    "dscto_igv": ("dsctoigvipm",),
    "total": ("totalcp", "importetotal", "total"),
    "moneda": ("moneda",),
}
OBLIGATORIAS = ("tipo_cp", "serie", "numero")
EXTENSIONES = ("txt", "csv", "zip", "xlsx")
ESTADO_ANULADO = "2"  # columna "Est. Comp" del RVIE


@dataclass
class LecturaSire:
    comprobantes: list[Comprobante] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


def leer_rvie(
    contenido: bytes, nombre_archivo: str, ruc_empresa: str, periodo: Optional[str] = None
) -> LecturaSire:
    """Si se indica periodo (AAAAMM), las filas de otro periodo se reportan como error."""
    filas = _filas(contenido, nombre_archivo)
    encabezado = next(filas, None)
    if encabezado is None:
        raise ValueError("El archivo está vacío")
    indices = _ubicar_columnas(encabezado)

    lectura = LecturaSire()
    for nro_fila, fila in enumerate(filas, start=2):
        if not any(n.texto(v) for v in fila):
            continue
        try:
            comprobante = _a_comprobante(fila, indices, ruc_empresa, periodo)
        except (ValueError, IndexError) as e:
            lectura.errores.append(f"Fila {nro_fila}: {e}")
            continue
        lectura.comprobantes.append(comprobante)
    return lectura


def _filas(contenido: bytes, nombre_archivo: str) -> Iterator[list]:
    extension = nombre_archivo.rsplit(".", 1)[-1].lower()
    if extension == "zip":
        return _filas_zip(contenido)
    if extension == "xlsx":
        return _filas_xlsx(contenido)
    if extension in ("txt", "csv"):
        return _filas_texto(contenido)
    raise ValueError(f"Extensión no soportada: .{extension} (se aceptan {', '.join(EXTENSIONES)})")


def _filas_zip(contenido: bytes) -> Iterator[list]:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        internos = [i for i in z.namelist() if i.rsplit(".", 1)[-1].lower() in ("txt", "csv", "xlsx")]
        if not internos:
            raise ValueError("El ZIP no contiene un archivo TXT, CSV o XLSX")
        interno = internos[0]
        datos = z.read(interno)
    return _filas(datos, interno)


def _filas_xlsx(contenido: bytes) -> Iterator[list]:
    import openpyxl  # solo se necesita para Excel

    libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    try:
        for fila in libro.active.iter_rows(values_only=True):
            yield ["" if v is None else v for v in fila]
    finally:
        libro.close()


def _filas_texto(contenido: bytes) -> Iterator[list]:
    texto = _decodificar(contenido)
    primera = texto.split("\n", 1)[0]
    delimitador = max(("|", ";", ",", "\t"), key=primera.count)
    return csv.reader(io.StringIO(texto), delimiter=delimitador)


def _decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("latin-1")


def _ubicar_columnas(encabezado: Iterable) -> dict[str, int]:
    posiciones = {n.nombre_columna(v): i for i, v in reversed(list(enumerate(encabezado)))}
    indices: dict[str, int] = {}
    for campo, alias in COLUMNAS.items():
        for a in alias:
            if a in posiciones:
                indices[campo] = posiciones[a]
                break
    faltantes = [c for c in OBLIGATORIAS if c not in indices]
    if faltantes:
        raise ValueError(f"No se encontraron las columnas obligatorias: {', '.join(faltantes)}")
    return indices


def _valor(fila: list, indices: dict[str, int], campo: str) -> Optional[object]:
    i = indices.get(campo)
    return None if i is None or i >= len(fila) else fila[i]


def _a_comprobante(fila: list, indices: dict[str, int], ruc_empresa: str, periodo: Optional[str]) -> Comprobante:
    ruc = ruc_empresa
    if "ruc" in indices:
        ruc = n.ruc(_valor(fila, indices, "ruc"))
        if ruc != ruc_empresa:
            raise ValueError(f"el RUC {ruc} no corresponde a la empresa {ruc_empresa}")
    if periodo and "periodo" in indices:
        periodo_fila = n.texto(_valor(fila, indices, "periodo"))
        if periodo_fila != periodo:
            raise ValueError(f"el periodo {periodo_fila} no corresponde al periodo {periodo}")
    tipo_cp = n.tipo_cp(_valor(fila, indices, "tipo_cp"))
    serie = n.serie(_valor(fila, indices, "serie"))
    numero = n.numero(_valor(fila, indices, "numero"))
    # El cruce es por CAR: el que trae el SIRE tiene que corresponder a la misma fila
    car = n.texto(_valor(fila, indices, "car")).upper()
    if car and car != armar_car(ruc, tipo_cp, serie, numero):
        raise ValueError(
            f"el CAR SUNAT {car} no corresponde a {tipo_cp} {serie}-{numero} (se esperaba {armar_car(ruc, tipo_cp, serie, numero)})"
        )
    return Comprobante(
        ruc=ruc,
        tipo_cp=tipo_cp,
        serie=serie,
        numero=numero,
        fecha_emision=n.fecha(_valor(fila, indices, "fecha_emision")),
        moneda=n.moneda(_valor(fila, indices, "moneda")),
        base_imponible=n.monto(_valor(fila, indices, "base_imponible")) + n.monto(_valor(fila, indices, "dscto_bi")),
        igv=n.monto(_valor(fila, indices, "igv")) + n.monto(_valor(fila, indices, "dscto_igv")),
        total=n.monto(_valor(fila, indices, "total")),
        doc_receptor=n.documento(_valor(fila, indices, "doc_receptor")),
        anulado=n.texto(_valor(fila, indices, "estado")) == ESTADO_ANULADO,
    )
