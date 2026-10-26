"""Mantenimiento de empresas (RUC emisores)."""

import flet as ft
import psycopg

from app.nucleo.db import conexion, empresa_repo
from app.nucleo.sire import normalizador as n
from app.nucleo.ui import componentes as c


async def construir(page: ft.Page, nav) -> ft.Control:
    ruc = ft.TextField(label="RUC", width=160, max_length=11)
    razon = ft.TextField(label="Razón social", width=360)
    tabla = c.tabla(["RUC", "Razón social", "Activa"])

    async def cargar():
        pool = await conexion.historial()
        async with pool.connection() as conn:
            empresas = await empresa_repo.listar(conn)
        tabla.rows = [
            c.fila(c.copiable(page, e["ruc"]), c.copiable(page, e["razon_social"]), ft.Switch(value=e["activo"], data=e["id"], on_change=cambiar_activo))
            for e in empresas
        ]

    async def cambiar_activo(e):
        pool = await conexion.historial()
        async with pool.connection() as conn:
            await empresa_repo.cambiar_activo(conn, e.control.data, e.control.value)

    async def agregar(_):
        try:
            valor_ruc = n.ruc(ruc.value)
        except ValueError as e:
            c.avisar(page, str(e), error=True)
            return
        if not razon.value.strip():
            c.avisar(page, "Ingrese la razón social", error=True)
            return
        pool = await conexion.historial()
        try:
            async with pool.connection() as conn:
                await empresa_repo.crear(conn, valor_ruc, razon.value.strip().upper())
        except psycopg.errors.UniqueViolation:
            c.avisar(page, f"El RUC {valor_ruc} ya está registrado", error=True)
            return
        ruc.value = razon.value = ""
        await cargar()
        c.avisar(page, "Empresa registrada")
        page.update()

    await cargar()
    return ft.Column(
        [
            c.titulo("Empresas"),
            ft.Row([ruc, razon, ft.FilledButton("Agregar", icon=ft.Icons.ADD, on_click=agregar)]),
            tabla,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
