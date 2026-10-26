"""Registro de procesos. Para agregar uno nuevo: crear su paquete y sumarlo aquí."""

from app.procesos import comparacion
from app.procesos.base import Proceso

REGISTRO: dict[str, Proceso] = {
    comparacion.PROCESO.codigo: comparacion.PROCESO,
}
