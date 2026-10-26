"""Cola de trabajos de todos los procesos, con progreso en vivo."""

import flet as ft

from app.nucleo.db import avisos, cola_repo, conexion
from app.nucleo.ui import componentes as c

REFRESCO_SEG = 5  # respaldo por si se pierde un aviso LISTEN


async def construir(page: ft.Page, nav) -> ft.Control:
    tabla = c.tabla(["#", "Proceso", "Empresa", "Periodo", "Estado", "Progreso", "Mensaje", "Creado", ""])

    def acciones(t) -> ft.Row:
        botones = []
        if t.estado == "OK":
            botones.append(ft.TextButton("Ver resultado", on_click=lambda _, t=t: page.run_task(nav.ir, t.proceso_codigo, trabajo_id=t.id)))
        if t.estado in ("ERROR", "CANCELADO"):
            botones.append(ft.TextButton("Reintentar", on_click=lambda _, t=t: page.run_task(reintentar, t.id)))
        if t.estado == "PENDIENTE":
            botones.append(ft.TextButton("Cancelar", on_click=lambda _, t=t: page.run_task(cancelar, t.id)))
        return ft.Row(botones)

    async def cargar():
        pool = await conexion.historial()
        async with pool.connection() as conn:
            trabajos = await cola_repo.listar(conn)
        tabla.rows = [
            c.fila(
                t.id,
                t.proceso_codigo,
                c.copiable(page, t.empresa_ruc, tooltip=t.empresa_nombre),
                t.periodo,
                c.etiqueta_estado(t.estado),
                ft.ProgressBar(value=t.progreso / 100, width=120),
                ft.Text(t.mensaje or "", width=380, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, tooltip=t.mensaje),
                t.creado_en.strftime("%d/%m/%Y %H:%M") if t.creado_en else "",
                acciones(t),
            )
            for t in trabajos
        ]

    async def reintentar(trabajo_id: int):
        pool = await conexion.historial()
        async with pool.connection() as conn:
            ok = await cola_repo.reintentar(conn, trabajo_id)
        c.avisar(page, "Trabajo reencolado" if ok else "El trabajo ya no se puede reintentar", error=not ok)

    async def cancelar(trabajo_id: int):
        pool = await conexion.historial()
        async with pool.connection() as conn:
            ok = await cola_repo.cancelar(conn, trabajo_id)
        c.avisar(page, "Trabajo cancelado" if ok else "El trabajo ya empezó y no se puede cancelar", error=not ok)

    async def refrescar():
        while True:
            await avisos.esperar(REFRESCO_SEG)
            await cargar()
            page.update()

    await cargar()
    nav.en_segundo_plano(refrescar)
    return ft.Column([c.titulo("Trabajos"), ft.Row([tabla], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO, expand=True)
