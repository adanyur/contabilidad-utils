"""Cruce SIRE vs Bizlinks en Python puro: no conoce la BD, la UI ni la cola."""

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional

from app.nucleo.modelos import Comprobante, Llave

COINCIDE = "COINCIDE"
DIFERENCIA = "DIFERENCIA"
SOLO_SIRE = "SOLO_SIRE"
SOLO_BIZLINKS = "SOLO_BIZLINKS"
ESTADOS = (COINCIDE, DIFERENCIA, SOLO_SIRE, SOLO_BIZLINKS)

# Los montos se comparan en valor absoluto: el SIRE registra las notas de crédito en negativo
# y los sistemas de emisión suelen guardarlas en positivo.
_MONTOS = ("base_imponible", "igv", "total")


@dataclass(frozen=True)
class ResultadoDetalle:
    llave: Llave
    estado: str
    sire: Optional[Comprobante]
    bizlinks: Optional[Comprobante]
    diferencias: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class ResultadoComparacion:
    detalles: list[ResultadoDetalle]
    total_sire: int
    total_bizlinks: int
    duplicados_sire: list[Llave]
    duplicados_bizlinks: list[Llave]

    @property
    def resumen(self) -> Counter:
        conteo = Counter({e: 0 for e in ESTADOS})
        conteo.update(d.estado for d in self.detalles)
        return conteo

    @property
    def solo_bizlinks_rechazados(self) -> int:
        """Rechazados por SUNAT: es esperable que no figuren en el SIRE."""
        return sum(1 for d in self.detalles if d.estado == SOLO_BIZLINKS and d.bizlinks.rechazado)

    @property
    def solo_bizlinks_pendientes(self) -> int:
        """Firmados o enviados sin respuesta de SUNAT: pueden no figurar aún en el SIRE."""
        return sum(1 for d in self.detalles if d.estado == SOLO_BIZLINKS and d.bizlinks.pendiente)


def comparar(
    sire: Iterable[Comprobante], bizlinks: Iterable[Comprobante], tolerancia: Decimal
) -> ResultadoComparacion:
    por_sire, dup_sire = _indexar(sire)
    por_biz, dup_biz = _indexar(bizlinks)

    detalles: list[ResultadoDetalle] = []
    for llave in sorted(por_sire.keys() | por_biz.keys()):
        s, b = por_sire.get(llave), por_biz.get(llave)
        if b is None:
            detalles.append(ResultadoDetalle(llave, SOLO_SIRE, s, None))
        elif s is None:
            detalles.append(ResultadoDetalle(llave, SOLO_BIZLINKS, None, b))
        else:
            diferencias = _diferencias(s, b, tolerancia)
            estado = DIFERENCIA if diferencias else COINCIDE
            detalles.append(ResultadoDetalle(llave, estado, s, b, diferencias))

    return ResultadoComparacion(
        detalles=detalles,
        total_sire=len(por_sire),
        total_bizlinks=len(por_biz),
        duplicados_sire=dup_sire,
        duplicados_bizlinks=dup_biz,
    )


def _indexar(comprobantes: Iterable[Comprobante]) -> tuple[dict[Llave, Comprobante], list[Llave]]:
    """Indexa por CAR; si un CAR se repite se conserva el primero y se reporta."""
    indice: dict[Llave, Comprobante] = {}
    duplicados: list[Llave] = []
    for c in comprobantes:
        if c.llave in indice:
            duplicados.append(c.llave)
        else:
            indice[c.llave] = c
    return indice, duplicados


def _diferencias(s: Comprobante, b: Comprobante, tolerancia: Decimal) -> dict[str, dict[str, str]]:
    dif: dict[str, dict[str, str]] = {}
    if b.rechazado:
        # Figura en el SIRE pero Bizlinks lo tiene como rechazado por SUNAT
        dif["estado_ose"] = {"sire": "REGISTRADO", "bizlinks": b.estado_ose}
    if s.fecha_emision and b.fecha_emision and s.fecha_emision != b.fecha_emision:
        dif["fecha_emision"] = {"sire": s.fecha_emision.isoformat(), "bizlinks": b.fecha_emision.isoformat()}
    if s.moneda and b.moneda and s.moneda != b.moneda:
        dif["moneda"] = {"sire": s.moneda, "bizlinks": b.moneda}
    if s.anulado != b.anulado:
        dif["anulado"] = {"sire": "SI" if s.anulado else "NO", "bizlinks": "SI" if b.anulado else "NO"}
    if s.anulado or b.anulado:
        # Un anulado figura con montos en cero en el SIRE: no se comparan montos
        return dif
    for campo in _MONTOS:
        vs, vb = getattr(s, campo), getattr(b, campo)
        if abs(abs(vs) - abs(vb)) > tolerancia:
            dif[campo] = {"sire": str(vs), "bizlinks": str(vb)}
    return dif
