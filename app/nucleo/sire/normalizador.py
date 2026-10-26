"""Normaliza los valores de ambos orígenes para que la llave y los montos sean comparables."""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

_FORMATOS_FECHA = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d")


def texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def ruc(valor) -> str:
    v = texto(valor)
    if not re.fullmatch(r"\d{11}", v):
        raise ValueError(f"RUC inválido: {v!r}")
    return v


def tipo_cp(valor) -> str:
    v = texto(valor)
    if not v.isdigit() or len(v) > 2:
        raise ValueError(f"Tipo de comprobante inválido: {v!r}")
    return v.zfill(2)


def serie(valor) -> str:
    v = texto(valor).upper()
    if not v:
        raise ValueError("Serie vacía")
    return v


def numero(valor) -> int:
    v = texto(valor)
    # Excel puede entregar el número como float ("123.0")
    if v.endswith(".0"):
        v = v[:-2]
    if not v.isdigit():
        raise ValueError(f"Número de comprobante inválido: {v!r}")
    return int(v)


def monto(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"))
    if isinstance(valor, (int, float)):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    v = texto(valor).replace(",", "").replace(" ", "")
    if not v:
        return Decimal("0.00")
    try:
        return Decimal(v).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"Monto inválido: {valor!r}") from None


def fecha(valor) -> Optional[date]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    v = texto(valor)
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(v, formato).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha inválida: {v!r}")


def moneda(valor) -> Optional[str]:
    v = texto(valor).upper()
    return v or None


def documento(valor) -> Optional[str]:
    v = texto(valor)
    return v or None


def nombre_columna(valor) -> str:
    """'Fecha de emisión' -> 'fechadeemision': sin tildes, espacios ni signos."""
    v = unicodedata.normalize("NFKD", texto(valor)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", v.lower())
