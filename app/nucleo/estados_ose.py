"""Catálogo de bl_estadoproceso de Bizlinks (spe_einvoice_response)."""

from typing import Optional

ACEPTADO = "ACEPTADO"
RECHAZADO = "RECHAZADO"
PENDIENTE = "PENDIENTE"  # firmado o enviado, sin respuesta final de SUNAT
ANULADO = "ANULADO"  # dado de baja
DESCONOCIDO = "DESCONOCIDO"

# estado normalizado -> (categoría, descripción)
CATALOGO: dict[str, tuple[str, str]] = {
    "SIGNED": (PENDIENTE, "Firmado"),
    "SIGNED/PE_02": (PENDIENTE, "Enviado a declarar (facturas y notas asociadas)"),
    "SIGNED/PE_09": (PENDIENTE, "Enviado a declarar (boletas y notas asociadas)"),
    "SIGNED/ED_06": (PENDIENTE, "En SUNAT sin respuesta (resúmenes)"),
    "SIGNED/AC_03": (ACEPTADO, "Aceptado por SUNAT"),
    "SIGNED/RC_05": (RECHAZADO, "Rechazado por SUNAT"),
    # No figura en el catálogo entregado; aparece en producción y coincide con los anulados del SIRE
    "SIGNED/AN_04": (ANULADO, "Anulado (dado de baja)"),
}


def normalizar(estado: Optional[str]) -> Optional[str]:
    """'SIGNED/ AC_03 ' -> 'SIGNED/AC_03' (el catálogo de Bizlinks trae espacios sueltos)."""
    if estado is None:
        return None
    v = "".join(estado.split()).upper()
    return v or None


def categoria(estado: Optional[str]) -> str:
    v = normalizar(estado)
    if v is None:
        return DESCONOCIDO
    return CATALOGO.get(v, (DESCONOCIDO, ""))[0]


def descripcion(estado: Optional[str]) -> str:
    v = normalizar(estado)
    if v is None:
        return ""
    return CATALOGO.get(v, (DESCONOCIDO, v))[1]
