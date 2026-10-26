"""Contrato mínimo que cumple cada proceso registrado."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.nucleo.modelos import Trabajo


class Contexto(Protocol):
    """Lo que el worker le ofrece al manejador mientras procesa un trabajo."""

    async def avance(self, progreso: int, mensaje: str) -> None: ...


@dataclass(frozen=True)
class Pantalla:
    """Opción de menú adicional de un proceso (ej. búsqueda de comprobantes de la comparación)."""

    codigo: str
    nombre: str
    icono: str  # nombre de ft.Icons
    vista: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Proceso:
    codigo: str  # igual a nucleo.proceso.codigo
    nombre: str
    icono: str  # nombre de ft.Icons
    cola: str  # cola pgmq
    # La vista se importa al construirla, así el worker no carga la UI
    vista: Callable[..., Awaitable[Any]]
    # Devuelve el mensaje final que se guarda en nucleo.trabajo
    manejador: Callable[[Trabajo, Contexto], Awaitable[str]]
    # Se agregan al menú a continuación del proceso
    pantallas: tuple[Pantalla, ...] = ()
