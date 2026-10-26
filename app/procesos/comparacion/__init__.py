from app.procesos.base import Pantalla, Proceso
from app.procesos.comparacion.manejador import ejecutar


async def _vista(*args, **kwargs):
    from app.procesos.comparacion import vistas

    return await vistas.construir(*args, **kwargs)


async def _vista_comprobantes(*args, **kwargs):
    from app.procesos.comparacion import vistas

    return await vistas.construir_comprobantes(*args, **kwargs)


async def _vista_periodos(*args, **kwargs):
    from app.procesos.comparacion import vistas

    return await vistas.construir_periodos(*args, **kwargs)


PROCESO = Proceso(
    codigo="COMPARACION",
    nombre="Comparación",
    icono="COMPARE_ARROWS",
    cola="comparacion",
    vista=_vista,
    manejador=ejecutar,
    pantallas=(
        Pantalla("PERIODOS", "Periodos", "EVENT_NOTE", _vista_periodos),
        Pantalla("COMPROBANTES", "Comprobantes", "RECEIPT_LONG", _vista_comprobantes),
    ),
)
