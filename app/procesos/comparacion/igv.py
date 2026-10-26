"""Fase 3: IGV calculado (base imponible x tasa) frente al IGV del SIRE y de Bizlinks. Python puro."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from app.nucleo.modelos import Comprobante, Llave
from app.procesos.comparacion.motor import ResultadoDetalle

CENTIMO = Decimal("0.01")


def calcular(base: Decimal, tasa: Decimal) -> Decimal:
    """IGV de la base gravada, en valor absoluto (las notas de crédito pueden venir en negativo)."""
    return (abs(base) * tasa).quantize(CENTIMO, ROUND_HALF_UP)


@dataclass(frozen=True)
class VerificacionIgv:
    llave: Llave
    sire_calculado: Optional[Decimal]  # None si no está en el SIRE o está anulado
    biz_calculado: Optional[Decimal]
    sire_observado: bool  # el IGV declarado se aparta del calculado más que la tolerancia
    biz_observado: bool

    @property
    def observado(self) -> bool:
        return self.sire_observado or self.biz_observado


def _lado(c: Optional[Comprobante], tasa: Decimal, tolerancia: Decimal) -> tuple[Optional[Decimal], bool]:
    if c is None or c.anulado:
        return None, False
    calculado = calcular(c.base_imponible, tasa)
    return calculado, abs(calculado - abs(c.igv)) > tolerancia


def verificar(detalles: Iterable[ResultadoDetalle], tasa: Decimal, tolerancia: Decimal) -> dict[Llave, VerificacionIgv]:
    resultado = {}
    for d in detalles:
        sire_calc, sire_obs = _lado(d.sire, tasa, tolerancia)
        biz_calc, biz_obs = _lado(d.bizlinks, tasa, tolerancia)
        resultado[d.llave] = VerificacionIgv(d.llave, sire_calc, biz_calc, sire_obs, biz_obs)
    return resultado
