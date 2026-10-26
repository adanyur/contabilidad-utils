"""Qué comprobantes necesitan sustento para poder cerrar el periodo. Python puro."""

from app.procesos.comparacion import motor
from app.procesos.comparacion.igv import VerificacionIgv
from app.procesos.comparacion.motor import ResultadoDetalle


def requiere(d: ResultadoDetalle, v: VerificacionIgv) -> bool:
    """Con diferencia, solo en SIRE, solo en Bizlinks (salvo rechazados por SUNAT) o con IGV observado."""
    if d.estado in (motor.DIFERENCIA, motor.SOLO_SIRE):
        return True
    if d.estado == motor.SOLO_BIZLINKS and not d.bizlinks.rechazado:
        return True
    return v.observado
