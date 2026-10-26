"""Aplicación web Flet.

    python -m app.main      (en Docker se levanta en modo web en el puerto FLET_SERVER_PORT)
"""

import logging

import flet as ft

from app import config
from app.nucleo.db import avisos
from app.nucleo.ui import empresas, trabajos
from app.procesos import REGISTRO

log = logging.getLogger("web")


class Navegador:
    """Cambia la vista del área de contenido y cancela las tareas de fondo de la vista anterior."""

    def __init__(self, page: ft.Page, contenido: ft.Container, menu: ft.NavigationRail, destinos: list):
        self.page = page
        self.contenido = contenido
        self.menu = menu
        self.destinos = destinos  # [(clave, construir)]
        self._tareas = []
        # Un solo FilePicker por sesión: los servicios de Flet quedan registrados en la página
        self.picker = ft.FilePicker()

    def en_segundo_plano(self, handler, *args) -> None:
        self._tareas.append(self.page.run_task(handler, *args))

    async def ir(self, clave: str, **kwargs) -> None:
        for tarea in self._tareas:
            tarea.cancel()
        self._tareas.clear()
        indice = next(i for i, (k, _) in enumerate(self.destinos) if k == clave)
        self.menu.selected_index = indice
        self.contenido.content = ft.ProgressRing()
        self.page.update()
        try:
            # No se envuelve en SelectionArea: en Flet 1.0 bloquea los botones de las tablas.
            # El texto copiable se marca con selectable=True (ver nucleo/ui/componentes.py).
            self.contenido.content = await self.destinos[indice][1](self.page, self, **kwargs)
        except Exception as e:
            log.exception("Error construyendo la vista %s", clave)
            self.contenido.content = ft.Text(f"No se pudo cargar la vista: {e}", color=ft.Colors.RED_700)
        self.page.update()


async def main(page: ft.Page) -> None:
    page.title = "Conciliación SIRE - Bizlinks"
    log.info("Sesión desde %s (%s)", page.url, page.client_ip)
    page.padding = 0
    avisos.iniciar()

    destinos = [("empresas", empresas.construir)]
    menu_items = [ft.NavigationRailDestination(icon=ft.Icons.BUSINESS, label="Empresas")]
    for proceso in REGISTRO.values():
        destinos.append((proceso.codigo, proceso.vista))
        menu_items.append(ft.NavigationRailDestination(icon=getattr(ft.Icons, proceso.icono), label=proceso.nombre))
        for pantalla in proceso.pantallas:
            destinos.append((pantalla.codigo, pantalla.vista))
            menu_items.append(ft.NavigationRailDestination(icon=getattr(ft.Icons, pantalla.icono), label=pantalla.nombre))
    destinos.append(("trabajos", trabajos.construir))
    menu_items.append(ft.NavigationRailDestination(icon=ft.Icons.PENDING_ACTIONS, label="Trabajos"))

    contenido = ft.Container(expand=True, padding=20)
    menu = ft.NavigationRail(destinations=menu_items, label_type=ft.NavigationRailLabelType.ALL, min_width=100)
    nav = Navegador(page, contenido, menu, destinos)

    async def cambiar(e):
        await nav.ir(destinos[e.control.selected_index][0])

    menu.on_change = cambiar
    page.add(ft.Row([menu, ft.VerticalDivider(width=1), contenido], expand=True))
    # Se abre en Comparación, el único proceso de la etapa 1
    await nav.ir(next(iter(REGISTRO)))


if __name__ == "__main__":
    cfg = config.cargar()
    config.configurar_logging(cfg)
    ft.run(main, view=ft.AppView.WEB_BROWSER)
