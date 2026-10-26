"""Piezas de UI reutilizadas por todas las vistas."""

from datetime import date
from typing import Optional

import flet as ft

COLOR_ESTADO = {
    "PENDIENTE": ft.Colors.GREY_600,
    "EN_PROCESO": ft.Colors.BLUE_700,
    "OK": ft.Colors.GREEN_700,
    "ERROR": ft.Colors.RED_700,
    "CANCELADO": ft.Colors.GREY_500,
    "COINCIDE": ft.Colors.GREEN_700,
    "DIFERENCIA": ft.Colors.ORANGE_800,
    "SOLO_SIRE": ft.Colors.RED_700,
    "SOLO_BIZLINKS": ft.Colors.PURPLE_700,
}


def avisar(page: ft.Page, texto: str, error: bool = False) -> None:
    page.show_dialog(ft.SnackBar(ft.Text(texto), bgcolor=ft.Colors.RED_700 if error else None))


def usuario(page: ft.Page) -> str:
    """Quién hizo la acción. Aún no hay inicio de sesión: se registra la IP del navegador."""
    return f"web {page.client_ip}" if page.client_ip else "web"


def copiable(page: ft.Page, valor, **kwargs) -> ft.Row:
    """Texto con botón para copiarlo al portapapeles (comprobante, RUC, razón social).

    Por http://IP solo copia entrando por nginx (puerto 80), que agrega docker/nginx/portapapeles.js.
    """
    texto = "" if valor is None else str(valor)

    def al_copiar(_):
        avisar(page, f"Copiado: {texto}")

    return ft.Row(
        [
            ft.Text(texto, selectable=True, **kwargs),
            ft.IconButton(
                ft.Icons.CONTENT_COPY,
                icon_size=14,
                tooltip="Copiar",
                # Lo copia el navegador dentro del clic, que es cuando permite escribir en el portapapeles
                action=ft.CopyToClipboard(texto),
                on_click=al_copiar,
            ),
        ],
        spacing=0,
        tight=True,
    )


def titulo(texto: str) -> ft.Text:
    return ft.Text(texto, size=22, weight=ft.FontWeight.BOLD)


def tarjeta(etiqueta: str, valor, color: Optional[str] = None) -> ft.Card:
    return ft.Card(
        content=ft.Container(
            ft.Column(
                [ft.Text(etiqueta, size=12), ft.Text(str(valor), size=24, weight=ft.FontWeight.BOLD, color=color)],
                spacing=4,
            ),
            padding=16,
            width=170,
        )
    )


def etiqueta_estado(estado: str) -> ft.Text:
    return ft.Text(estado, color=COLOR_ESTADO.get(estado), weight=ft.FontWeight.BOLD)


def selector_empresa(empresas: list[dict], **kwargs) -> ft.Dropdown:
    """Si hay una sola empresa queda seleccionada; con varias el usuario elige."""
    return ft.Dropdown(
        label="Empresa",
        width=380,
        options=[ft.DropdownOption(key=str(e["id"]), text=f"{e['ruc']} - {e['razon_social']}") for e in empresas],
        value=str(empresas[0]["id"]) if len(empresas) == 1 else None,
        **kwargs,
    )


MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre")


def periodos(cantidad: int = 13, hoy: Optional[date] = None) -> list[str]:
    """Periodos AAAAMM desde el mes en curso hacia atrás."""
    hoy = hoy or date.today()
    indice = hoy.year * 12 + hoy.month - 1
    return [f"{i // 12}{i % 12 + 1:02d}" for i in range(indice, indice - cantidad, -1)]


def selector_periodo(**kwargs) -> ft.Dropdown:
    """Lista de periodos con el mes en curso seleccionado."""
    lista = periodos()
    return ft.Dropdown(
        label="Periodo",
        width=220,
        options=[ft.DropdownOption(key=p, text=f"{MESES[int(p[4:]) - 1]} {p[:4]}") for p in lista],
        value=lista[0],
        **kwargs,
    )


def tabla(columnas: list[str]) -> ft.DataTable:
    return ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in columnas], rows=[])


def fila(*valores) -> ft.DataRow:
    return ft.DataRow(
        # Las celdas de texto se pueden seleccionar con el mouse y copiar con Ctrl+C
        cells=[
            ft.DataCell(v if isinstance(v, ft.Control) else ft.Text("" if v is None else str(v), selectable=True))
            for v in valores
        ]
    )
