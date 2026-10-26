"""Fase 2: totales por tipo de comprobante y moneda, SIRE frente a Bizlinks. Python puro.

No suman los anulados (el SIRE los registra en cero) ni los rechazados por SUNAT (no son comprobantes
válidos). Las notas de crédito restan: el SIRE ya las trae en negativo y Bizlinks en positivo.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from app.nucleo.modelos import Comprobante
from app.procesos.comparacion import igv

TOTAL = "TOTAL"  # fila que suma todos los tipos de una moneda
NOTA_CREDITO = "07"
_CAMPOS = ("cantidad", "base", "igv", "total", "igv_calculado")


@dataclass
class Acumulado:
    cantidad: int = 0
    base: Decimal = Decimal("0")
    igv: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    igv_calculado: Decimal = Decimal("0")

    def sumar(self, c: Comprobante, tasa: Decimal) -> None:
        signo = -1 if c.tipo_cp == NOTA_CREDITO else 1
        self.cantidad += 1
        self.base += signo * abs(c.base_imponible)
        self.igv += signo * abs(c.igv)
        self.total += signo * abs(c.total)
        self.igv_calculado += signo * igv.calcular(c.base_imponible, tasa)


@dataclass
class FilaTotales:
    tipo_cp: str  # "01", "03", "07", "08" o TOTAL
    moneda: str
    sire: Acumulado = field(default_factory=Acumulado)
    bizlinks: Acumulado = field(default_factory=Acumulado)

    def diferencias(self, tolerancia: Decimal) -> dict[str, dict[str, str]]:
        dif = {}
        for campo in _CAMPOS:
            vs, vb = getattr(self.sire, campo), getattr(self.bizlinks, campo)
            if abs(vs - vb) > (0 if campo == "cantidad" else tolerancia):
                dif[campo] = {"sire": str(vs), "bizlinks": str(vb)}
        return dif


@dataclass
class ResultadoTotales:
    filas: list[FilaTotales]
    excluidos_sire: int  # anulados
    excluidos_bizlinks: int  # anulados y rechazados


def calcular(sire: Iterable[Comprobante], bizlinks: Iterable[Comprobante], tasa: Decimal) -> ResultadoTotales:
    filas: dict[tuple[str, str], FilaTotales] = {}

    def fila(tipo_cp: str, moneda: str) -> FilaTotales:
        return filas.setdefault((tipo_cp, moneda), FilaTotales(tipo_cp, moneda))

    excluidos = {"sire": 0, "bizlinks": 0}
    for lado, comprobantes in (("sire", sire), ("bizlinks", bizlinks)):
        for c in comprobantes:
            if c.anulado or c.rechazado:
                excluidos[lado] += 1
                continue
            moneda = c.moneda or "PEN"
            getattr(fila(c.tipo_cp, moneda), lado).sumar(c, tasa)
            getattr(fila(TOTAL, moneda), lado).sumar(c, tasa)

    # Tipos en orden y la fila TOTAL al final de cada moneda
    orden = sorted(filas.values(), key=lambda f: (f.moneda, f.tipo_cp == TOTAL, f.tipo_cp))
    return ResultadoTotales(orden, excluidos["sire"], excluidos["bizlinks"])
