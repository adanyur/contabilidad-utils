"""Modelos compartidos por todos los procesos."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from app.nucleo import estados_ose

Llave = str  # CAR SUNAT: RUC (11) + tipo (2) + serie (4) + número con ceros (10) = 27 caracteres


def armar_car(ruc: str, tipo_cp: str, serie: str, numero: int) -> str:
    """Código de Anotación de Registro, igual al que trae el SIRE en la columna "CAR SUNAT"."""
    return f"{ruc}{tipo_cp}{serie}{numero:010d}"


@dataclass(frozen=True)
class Comprobante:
    ruc: str
    tipo_cp: str
    serie: str
    numero: int
    fecha_emision: Optional[date] = None
    moneda: Optional[str] = None
    base_imponible: Decimal = Decimal("0")
    igv: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    doc_receptor: Optional[str] = None
    # En el SIRE un comprobante anulado (Est. Comp = 2) figura con montos en cero
    anulado: bool = False
    # Solo lado Bizlinks: bl_estadoproceso (ej. "SIGNED/AC_03") y respuesta de SUNAT
    estado_ose: Optional[str] = None
    mensaje_sunat: Optional[str] = None

    @property
    def llave(self) -> Llave:
        """El cruce SIRE vs Bizlinks es por CAR; Bizlinks no lo guarda y se arma con sus datos."""
        return armar_car(self.ruc, self.tipo_cp, self.serie, self.numero)

    @property
    def rechazado(self) -> bool:
        return estados_ose.categoria(self.estado_ose) == estados_ose.RECHAZADO

    @property
    def pendiente(self) -> bool:
        return estados_ose.categoria(self.estado_ose) == estados_ose.PENDIENTE


@dataclass
class Trabajo:
    id: int
    proceso_codigo: str
    empresa_id: int
    periodo: str
    carga_archivo_id: Optional[int]
    parametros: dict[str, Any] = field(default_factory=dict)
    estado: str = "PENDIENTE"
    progreso: int = 0
    mensaje: Optional[str] = None
    intentos: int = 0
    max_intentos: int = 3
    msg_id: Optional[int] = None
    creado_en: Optional[datetime] = None
    finalizado_en: Optional[datetime] = None
    empresa_ruc: Optional[str] = None
    empresa_nombre: Optional[str] = None
