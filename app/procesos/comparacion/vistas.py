"""Pantallas del proceso de comparación: nueva comparación, resultado y búsqueda de comprobantes."""

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

import flet as ft

from app import config
from app.nucleo import estados_ose, exportar
from app.nucleo.db import carga_repo, cola_repo, conexion, empresa_repo
from app.nucleo.sire import lector
from app.nucleo.ui import componentes as c
from app.procesos.comparacion import motor, periodo_repo, repo, totales
from app.procesos.comparacion.parametros import ParametrosFases

CODIGO = "COMPARACION"
POR_PAGINA = 50


async def construir(page: ft.Page, nav, trabajo_id: int | None = None) -> ft.Control:
    if trabajo_id is not None:
        return await _resultado(page, nav, trabajo_id)
    return ft.Column([_nueva(page, nav, await _empresas())], scroll=ft.ScrollMode.AUTO, expand=True)


async def construir_comprobantes(page: ft.Page, nav) -> ft.Control:
    """Menú Comprobantes: en qué comparaciones aparece un comprobante y con qué resultado."""
    return ft.Column([_historial(page, await _empresas())], scroll=ft.ScrollMode.AUTO, expand=True)


async def _empresas() -> list[dict]:
    pool = await conexion.historial()
    async with pool.connection() as conn:
        return await empresa_repo.listar(conn, solo_activas=True)


# --- nueva comparación ---------------------------------------------------------------------

def _nueva(page: ft.Page, nav, empresas: list[dict]) -> ft.Control:
    cfg = config.cargar()
    empresa = c.selector_empresa(empresas)
    periodo = c.selector_periodo()
    archivo_texto = ft.Text("Ningún archivo seleccionado")
    seleccionado: dict = {}
    picker = nav.picker

    async def elegir(_):
        archivos = await picker.pick_files(
            dialog_title="Archivo SIRE RVIE",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=list(lector.EXTENSIONES),
            with_data=True,
        )
        if not archivos:
            return
        a = archivos[0]
        if a.size > cfg.max_archivo_mb * 1024 * 1024:
            c.avisar(page, f"El archivo supera {cfg.max_archivo_mb} MB", error=True)
            return
        seleccionado.update(nombre=a.name, contenido=a.bytes)
        archivo_texto.value = f"{a.name} ({a.size / 1024:.1f} KB)"
        page.update()

    async def encolar(_):
        if not empresa.value:
            c.avisar(page, "Seleccione la empresa", error=True)
            return
        if not periodo.value:
            c.avisar(page, "Seleccione el periodo", error=True)
            return
        if not seleccionado:
            c.avisar(page, "Seleccione el archivo SIRE", error=True)
            return
        empresa_id = int(empresa.value)
        pool = await conexion.historial()
        async with pool.connection() as conn:
            cabecera = await periodo_repo.obtener(conn, empresa_id, periodo.value)
            previo = await carga_repo.trabajo_previo_ok(
                conn, empresa_id, periodo.value, carga_repo.calcular_hash(seleccionado["contenido"])
            )
        if cabecera and cabecera["estado"] == periodo_repo.CERRADO:
            c.avisar(page, f"El periodo {periodo.value} está cerrado. Reábralo en Periodos para volver a cargar.",
                     error=True)
            return
        avisos = []
        if previo:
            avisos.append(f"Este mismo archivo ya se comparó en el trabajo #{previo}.")
        if cabecera and cabecera["trabajo_vigente_id"]:
            avisos.append(
                f"El periodo ya tiene la carga #{cabecera['trabajo_vigente_id']}: la nueva carga reemplazará el "
                "detalle. Los sustentos registrados se conservan."
            )
        if avisos:
            _confirmar(page, " ".join(avisos) + " ¿Continuar?", lambda: page.run_task(_enviar, empresa_id))
        else:
            await _enviar(empresa_id)

    async def _enviar(empresa_id: int):
        pool = await conexion.historial()
        async with pool.connection() as conn:
            async with conn.transaction():
                await periodo_repo.obtener_o_crear(conn, empresa_id, periodo.value)
                carga_id = await carga_repo.insertar(
                    conn, empresa_id, periodo.value, "SIRE_RVIE",
                    seleccionado["nombre"], seleccionado["contenido"], usuario=c.usuario(page),
                )
                trabajo_id = await cola_repo.encolar(
                    conn, CODIGO, empresa_id, periodo.value, carga_id,
                    ParametrosFases.desde_config().a_dict(), cfg.max_intentos, usuario=c.usuario(page),
                )
        seleccionado.clear()
        c.avisar(page, f"Comparación encolada (trabajo #{trabajo_id})")
        await nav.ir("trabajos")

    return ft.Column(
        [
            c.titulo("Nueva comparación SIRE (RVIE) vs Bizlinks"),
            ft.Text("Formatos: TXT o CSV exportado del SIRE, ZIP descargado de SUNAT o XLSX."),
            ft.Row([empresa, periodo], wrap=True),
            ft.Row([ft.OutlinedButton("Seleccionar archivo", icon=ft.Icons.UPLOAD_FILE, on_click=elegir), archivo_texto]),
            ft.FilledButton("Encolar comparación", icon=ft.Icons.PLAY_ARROW, on_click=encolar),
        ]
    )


def _confirmar(page: ft.Page, texto: str, al_aceptar) -> None:
    def aceptar(_):
        page.pop_dialog()
        al_aceptar()

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar"),
            content=ft.Text(texto),
            actions=[ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()), ft.FilledButton("Continuar", on_click=aceptar)],
        )
    )


# --- búsqueda de comprobantes (menú Comprobantes) ------------------------------------------

def _historial(page: ft.Page, empresas: list[dict]) -> ft.Control:
    empresa = c.selector_empresa(empresas)
    serie = ft.TextField(label="Serie", width=120)
    numero = ft.TextField(label="Número", width=140)
    car = ft.TextField(label="o CAR SUNAT", width=290, max_length=27)
    tabla = c.tabla(["Trabajo", "Periodo", "Fecha", "CAR SUNAT", "Tipo", "Comprobante", "Estado", "Diferencias",
                     "Sustento"])

    async def buscar(_):
        valor_car = car.value.strip().upper()
        if not empresa.value:
            c.avisar(page, "Seleccione la empresa", error=True)
            return
        if valor_car:
            criterio = {"car": valor_car}
        elif serie.value.strip() and numero.value.strip().isdigit():
            criterio = {"serie": serie.value.strip().upper(), "numero": int(numero.value)}
        else:
            c.avisar(page, "Indique serie y número, o el CAR SUNAT", error=True)
            return
        pool = await conexion.historial()
        async with pool.connection() as conn:
            filas = await repo.historial_comprobante(conn, int(empresa.value), **criterio)
        tabla.rows = [
            c.fila(
                f["trabajo_id"], f["periodo"], f["finalizado_en"].strftime("%d/%m/%Y %H:%M"),
                c.copiable(page, f["car"]), f["tipo_cp"], c.copiable(page, _comprobante(f)),
                c.etiqueta_estado(f["estado"]), _texto_diferencias(f["diferencias"]),
                _texto_sustento(f),
            )
            for f in filas
        ]
        if not filas:
            c.avisar(page, "El comprobante no aparece en la carga vigente de ningún periodo")
        page.update()

    serie.on_submit = numero.on_submit = car.on_submit = buscar
    return ft.Column(
        [
            c.titulo("Buscar comprobante"),
            ft.Text("Muestra el resultado del comprobante en la carga vigente de cada periodo y su sustento."),
            ft.Row([empresa, serie, numero, car, ft.FilledButton("Buscar", icon=ft.Icons.SEARCH, on_click=buscar)],
                   wrap=True),
            tabla,
        ]
    )


# --- resultado de un trabajo ---------------------------------------------------------------

async def _resultado(page: ft.Page, nav, trabajo_id: int) -> ft.Control:
    pool = await conexion.historial()
    async with pool.connection() as conn:
        trabajo = await cola_repo.obtener(conn, trabajo_id)
        resumen = await repo.resumen(conn, trabajo_id)
        filas_totales = await repo.totales(conn, trabajo_id)
        cabecera = await periodo_repo.obtener(conn, trabajo.empresa_id, trabajo.periodo) if trabajo else None
        motivos = await periodo_repo.motivos(conn)
    if trabajo is None or resumen is None:
        return ft.Text(f"El trabajo #{trabajo_id} no tiene resultado")

    vigente = cabecera is not None and cabecera["trabajo_vigente_id"] == trabajo_id
    secciones: list[ft.Control] = []
    barra = ft.Column()

    async def recargar():
        """Tras sustentar, cerrar o reabrir: refresca la cabecera y la pestaña visible."""
        nonlocal cabecera
        async with pool.connection() as conn:
            cabecera = await periodo_repo.obtener(conn, trabajo.empresa_id, trabajo.periodo)
        barra.controls = [_barra_periodo(page, pool, cabecera, vigente, nav, recargar)]
        if contenido.content.data:
            await contenido.content.data()
        page.update()

    def sustentar(f: dict):
        if not vigente:
            c.avisar(page, "Solo se sustenta sobre la carga vigente del periodo", error=True)
            return
        _dialogo_sustento(page, pool, cabecera, f, motivos, recargar)

    secciones += [
        _fase_comprobantes(page, nav, pool, trabajo, resumen, sustentar),
        _fase_totales(resumen, filas_totales),
        _fase_igv(page, nav, pool, trabajo, resumen, filas_totales, sustentar),
    ]
    contenido = ft.Container(secciones[0], padding=ft.Padding(0, 12, 0, 0))

    async def cambiar(e):
        seccion = secciones[e.control.selected_index]
        contenido.content = seccion
        page.update()
        if seccion.data:  # las fases con listado recargan su página al entrar
            await seccion.data()

    pestanas = ft.Tabs(
        length=len(secciones),
        on_change=cambiar,
        content=ft.TabBar(
            scrollable=False,
            tab_alignment=ft.TabAlignment.FILL,
            tabs=[
                ft.Tab(label="1 · Comprobantes", icon=ft.Icons.COMPARE_ARROWS),
                ft.Tab(label="2 · Totales", icon=ft.Icons.FUNCTIONS),
                ft.Tab(label="3 · Cálculo de IGV", icon=ft.Icons.CALCULATE),
            ],
        ),
    )
    barra.controls = [_barra_periodo(page, pool, cabecera, vigente, nav, recargar)]
    await secciones[0].data()  # carga la primera página de la fase 1
    return ft.Column(
        [
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: page.run_task(nav.ir, "PERIODOS")),
                    c.titulo(f"Resultado #{trabajo_id} · periodo {trabajo.periodo}")]),
            ft.Row([c.copiable(page, trabajo.empresa_ruc, weight=ft.FontWeight.BOLD),
                    c.copiable(page, trabajo.empresa_nombre)], wrap=True),
            barra,
            pestanas,
            contenido,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


# Cabecera del periodo: estado, sustentos pendientes, cierre y reapertura

COLOR_SUSTENTO = {periodo_repo.PENDIENTE: ft.Colors.ORANGE_800, periodo_repo.EN_CORRECCION: ft.Colors.BLUE_700,
                  periodo_repo.SUSTENTADO: ft.Colors.GREEN_700}
COLOR_PERIODO = {periodo_repo.ABIERTO: ft.Colors.BLUE_700, periodo_repo.CERRADO: ft.Colors.GREEN_700}


def _barra_periodo(page: ft.Page, pool, cabecera: Optional[dict], vigente: bool, nav, al_cambiar) -> ft.Control:
    if cabecera is None:
        return ft.Text("Este trabajo no tiene cabecera de periodo", color=ft.Colors.ORANGE_800)
    if not vigente:
        return ft.Row(
            [
                ft.Icon(ft.Icons.HISTORY, color=ft.Colors.ORANGE_800),
                ft.Text(f"Esta carga fue reemplazada por la carga #{cabecera['trabajo_vigente_id']}: su detalle ya "
                        "no se conserva y no admite sustentos.", color=ft.Colors.ORANGE_800),
                ft.TextButton("Ver carga vigente", on_click=lambda _: page.run_task(
                    nav.ir, CODIGO, trabajo_id=cabecera["trabajo_vigente_id"])),
            ],
            wrap=True,
        )
    cerrado = cabecera["estado"] == periodo_repo.CERRADO
    detalle = (f"Cerrado el {cabecera['cerrado_en']:%d/%m/%Y %H:%M} por {cabecera['cerrado_por'] or '-'}" if cerrado
               else f"Por sustentar: {cabecera['pendientes']} de {cabecera['requieren_sustento']} que lo requieren")
    acciones = [ft.TextButton("Bitácora", icon=ft.Icons.LIST_ALT,
                              on_click=lambda _: page.run_task(_dialogo_bitacora, page, pool, cabecera))]
    if cerrado:
        acciones.append(ft.OutlinedButton("Reabrir periodo", icon=ft.Icons.LOCK_OPEN,
                                          on_click=lambda _: _dialogo_cierre(page, pool, cabecera, False, al_cambiar)))
    else:
        acciones.append(ft.FilledButton("Cerrar periodo", icon=ft.Icons.LOCK, disabled=cabecera["pendientes"] > 0,
                                        tooltip="Se habilita cuando no quedan comprobantes por sustentar",
                                        on_click=lambda _: _dialogo_cierre(page, pool, cabecera, True, al_cambiar)))
    return ft.Container(
        ft.Row(
            [
                ft.Icon(ft.Icons.LOCK if cerrado else ft.Icons.LOCK_OPEN, color=COLOR_PERIODO[cabecera["estado"]]),
                ft.Text(f"Periodo {cabecera['estado'].lower()}", weight=ft.FontWeight.BOLD,
                        color=COLOR_PERIODO[cabecera["estado"]]),
                ft.Text(detalle),
                *acciones,
            ],
            wrap=True,
        ),
        padding=ft.Padding(12, 8, 12, 8),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
    )


def _texto_sustento(f: dict) -> ft.Control:
    estado = f["sustento_estado"] or (periodo_repo.PENDIENTE if f["requiere_sustento"] else None)
    if estado is None:
        return ft.Text("")
    return ft.Text(periodo_repo.ESTADOS_SUSTENTO[estado], color=COLOR_SUSTENTO[estado], weight=ft.FontWeight.BOLD)


def _celda_sustento(f: dict, sustentar) -> ft.Control:
    """Estado del sustento con botón para editarlo; vacío si el comprobante no lo necesita."""
    estado = f["sustento_estado"] or (periodo_repo.PENDIENTE if f["requiere_sustento"] else None)
    if estado is None:
        return ft.Text("")
    tooltip = " · ".join(v for v in (f["sustento_motivo"], f["sustento_comentario"], f["sustento_usuario"]) if v)
    return ft.Row(
        [
            ft.Text(periodo_repo.ESTADOS_SUSTENTO[estado], color=COLOR_SUSTENTO[estado], weight=ft.FontWeight.BOLD,
                    tooltip=tooltip or None),
            ft.IconButton(ft.Icons.EDIT_NOTE, icon_size=18, tooltip="Sustentar", on_click=lambda _: sustentar(f)),
        ],
        spacing=0,
        tight=True,
    )


def _dialogo_sustento(page: ft.Page, pool, cabecera: dict, f: dict, motivos: list[dict], al_guardar) -> None:
    cerrado = cabecera["estado"] == periodo_repo.CERRADO
    estado = ft.Dropdown(
        label="Estado", width=220, value=f["sustento_estado"] or periodo_repo.PENDIENTE, disabled=cerrado,
        options=[ft.DropdownOption(key=k, text=v) for k, v in periodo_repo.ESTADOS_SUSTENTO.items()],
    )
    motivo = ft.Dropdown(
        label="Motivo", width=460, value=f["sustento_motivo"], disabled=cerrado,
        options=[ft.DropdownOption(key=m["codigo"], text=m["descripcion"]) for m in motivos],
    )
    comentario = ft.TextField(label="Comentario", value=f["sustento_comentario"] or "", multiline=True,
                              min_lines=3, max_lines=6, width=460, disabled=cerrado)
    historial = ft.Column(spacing=2)

    async def cargar_historial():
        async with pool.connection() as conn:
            filas = await periodo_repo.historial_sustento(conn, cabecera["id"], f["car"])
        historial.controls = [
            ft.Text(f"{h['creado_en']:%d/%m/%Y %H:%M} · {periodo_repo.ESTADOS_SUSTENTO[h['estado']]}"
                    f"{' · ' + h['motivo'] if h['motivo'] else ''} · {h['usuario'] or '-'}"
                    f"{' · ' + h['comentario'] if h['comentario'] else ''}", size=12)
            for h in filas
        ] or [ft.Text("Sin cambios registrados", size=12)]
        page.update()

    async def guardar(_):
        try:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await periodo_repo.guardar_sustento(
                        conn, cabecera["id"], f["car"], estado.value, motivo.value,
                        comentario.value.strip() or None, c.usuario(page),
                    )
        except ValueError as e:
            c.avisar(page, str(e), error=True)
            return
        page.pop_dialog()
        c.avisar(page, f"Sustento guardado: {_comprobante(f)}")
        await al_guardar()

    diferencias = _texto_diferencias(f["diferencias"])
    if f.get("igv_observado"):
        diferencias = "; ".join(v for v in (diferencias, "IGV observado (fase 3)") if v)
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Sustento · {_comprobante(f)}"),
            content=ft.Column(
                [
                    c.copiable(page, f["car"]),
                    ft.Text(f"Resultado: {f['estado']}" + (f" · {diferencias}" if diferencias else "")),
                    estado, motivo, comentario,
                    ft.Text("Historial", weight=ft.FontWeight.BOLD),
                    historial,
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=500,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton("Guardar", on_click=guardar, disabled=cerrado),
            ],
        )
    )
    page.run_task(cargar_historial)


def _dialogo_cierre(page: ft.Page, pool, cabecera: dict, cerrar: bool, al_cambiar) -> None:
    comentario = ft.TextField(label="Comentario" + ("" if cerrar else " (obligatorio)"), multiline=True,
                              min_lines=2, width=420)

    async def confirmar(_):
        async with pool.connection() as conn:
            async with conn.transaction():
                if cerrar:
                    error = await periodo_repo.cerrar(conn, cabecera["id"], c.usuario(page),
                                                      comentario.value.strip() or None)
                else:
                    error = await periodo_repo.reabrir(conn, cabecera["id"], c.usuario(page), comentario.value)
        if error:
            c.avisar(page, error, error=True)
            return
        page.pop_dialog()
        c.avisar(page, f"Periodo {cabecera['periodo']} {'cerrado' if cerrar else 'reabierto'}")
        await al_cambiar()

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{'Cerrar' if cerrar else 'Reabrir'} periodo {cabecera['periodo']}"),
            content=ft.Column(
                [
                    ft.Text("Cerrado, el periodo no admite nuevas cargas ni cambios de sustento hasta reabrirlo."
                            if cerrar else "Al reabrir se podrá volver a cargar el SIRE y cambiar sustentos."),
                    comentario,
                ],
                tight=True,
                width=440,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton("Cerrar periodo" if cerrar else "Reabrir", on_click=confirmar),
            ],
        )
    )


async def _dialogo_bitacora(page: ft.Page, pool, cabecera: dict) -> None:
    async with pool.connection() as conn:
        eventos = await periodo_repo.eventos(conn, cabecera["id"])
    tabla = c.tabla(["Fecha", "Evento", "Carga", "Usuario", "Comentario"])
    tabla.rows = [
        c.fila(e["creado_en"].strftime("%d/%m/%Y %H:%M") if e["creado_en"] else "", e["tipo"],
               f"#{e['trabajo_id']}" if e["trabajo_id"] else "", e["usuario"], e["comentario"])
        for e in eventos
    ]
    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(f"Bitácora del periodo {cabecera['periodo']}"),
            content=ft.Column([ft.Row([tabla], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO, width=800),
            actions=[ft.TextButton("Cerrar", on_click=lambda _: page.pop_dialog())],
        )
    )


# --- periodos (menú Periodos) ----------------------------------------------------------------

async def construir_periodos(page: ft.Page, nav) -> ft.Control:
    """Cabeceras por empresa + periodo: carga vigente, sustentos pendientes y estado de cierre."""
    pool = await conexion.historial()
    tabla = c.tabla(["", "Empresa", "Periodo", "Estado", "Carga vigente", "Cargas", "Requieren sustento",
                     "Por sustentar"])

    def ver(p: dict):
        if not p["trabajo_vigente_id"]:
            c.avisar(page, f"El periodo {p['periodo']} aún no tiene una carga terminada", error=True)
            return
        page.run_task(nav.ir, CODIGO, trabajo_id=p["trabajo_vigente_id"])

    async def cargar():
        async with pool.connection() as conn:
            periodos = await periodo_repo.listar(conn)
        tabla.rows = [
            c.fila(
                ft.Row(
                    [
                        ft.TextButton("Ver", on_click=lambda _, p=p: ver(p)),
                        ft.TextButton("Bitácora", on_click=lambda _, p=p: page.run_task(_dialogo_bitacora, page, pool, p)),
                    ],
                    spacing=0,
                ),
                c.copiable(page, p["empresa_ruc"], tooltip=p["empresa_nombre"]),
                p["periodo"],
                ft.Text(p["estado"], color=COLOR_PERIODO[p["estado"]], weight=ft.FontWeight.BOLD),
                f"#{p['trabajo_vigente_id']} · {p['vigente_en']:%d/%m/%Y %H:%M}" if p["trabajo_vigente_id"] and p["vigente_en"]
                else "Sin carga terminada",
                p["cargas"],
                p["requieren_sustento"],
                ft.Text(str(p["pendientes"]),
                        color=ft.Colors.ORANGE_800 if p["pendientes"] else c.COLOR_ESTADO["COINCIDE"],
                        weight=ft.FontWeight.BOLD),
            )
            for p in periodos
        ]
        page.update()

    await cargar()
    return ft.Column(
        [
            c.titulo("Periodos"),
            ft.Text("Una cabecera por empresa y periodo. Cada nueva carga del SIRE reemplaza el detalle; los sustentos "
                    "se conservan. El periodo se cierra desde su resultado cuando no quedan comprobantes por sustentar."),
            ft.Row([tabla], scroll=ft.ScrollMode.AUTO),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


# Fase 1: comprobante por comprobante

def _fase_comprobantes(page: ft.Page, nav, pool, trabajo, resumen: dict, sustentar) -> ft.Control:
    estado = ft.Dropdown(
        label="Estado",
        width=220,
        value="",
        options=[ft.DropdownOption(key="", text="Todos")] + [ft.DropdownOption(key=e, text=e) for e in motor.ESTADOS],
    )
    filtro_sustento = ft.Dropdown(
        label="Sustento",
        width=260,
        value="",
        options=[
            ft.DropdownOption(key="", text="Todos"),
            ft.DropdownOption(key="PENDIENTES", text="Por sustentar (impiden cerrar)"),
            ft.DropdownOption(key="REQUIERE", text="Requieren sustento"),
            ft.DropdownOption(key="PENDIENTE", text="Pendiente"),
            ft.DropdownOption(key="EN_CORRECCION", text="En corrección"),
            ft.DropdownOption(key="SUSTENTADO", text="Sustentado"),
        ],
    )
    columnas = ["CAR SUNAT", "Tipo", "Comprobante", "Estado", "Sustento", "Fecha SIRE", "Total SIRE",
                "Fecha Bizlinks", "Total Bizlinks", "Estado Bizlinks", "Diferencias"]

    def fila(f: dict) -> ft.DataRow:
        return c.fila(
            c.copiable(page, f["car"]), f["tipo_cp"], c.copiable(page, _comprobante(f)), c.etiqueta_estado(f["estado"]),
            _celda_sustento(f, sustentar),
            f["sire_fecha"], _total(f["sire_total"], f["sire_anulado"]),
            f["biz_fecha"], _total(f["biz_total"], f["biz_anulado"]),
            ft.Text(
                estados_ose.descripcion(f["biz_estado"]),
                tooltip=" · ".join(v for v in (f["biz_estado"], f["biz_mensaje_sunat"]) if v) or None,
            ),
            _texto_diferencias(f["diferencias"]),
        )

    listado = _listado(page, nav, pool, trabajo, columnas, fila,
                       lambda: {"estado": estado.value or None, "sustento": filtro_sustento.value or None})

    async def filtrar(_):
        await listado.data(reiniciar=True)

    estado.on_select = filtro_sustento.on_select = filtrar
    tarjetas = ft.Row(
        [
            c.tarjeta("Comprobantes SIRE", resumen["total_sire"]),
            c.tarjeta("Comprobantes Bizlinks", resumen["total_bizlinks"]),
            c.tarjeta("Coinciden", resumen["coinciden"], c.COLOR_ESTADO["COINCIDE"]),
            c.tarjeta("Con diferencia", resumen["con_diferencia"], c.COLOR_ESTADO["DIFERENCIA"]),
            c.tarjeta("Solo en SIRE", resumen["solo_sire"], c.COLOR_ESTADO["SOLO_SIRE"]),
            c.tarjeta("Solo en Bizlinks", resumen["solo_bizlinks"], c.COLOR_ESTADO["SOLO_BIZLINKS"]),
            c.tarjeta("…rechazados por SUNAT", resumen["solo_bizlinks_rechazados"], c.COLOR_ESTADO["CANCELADO"]),
            c.tarjeta("…sin respuesta SUNAT", resumen["solo_bizlinks_pendientes"], c.COLOR_ESTADO["CANCELADO"]),
        ],
        wrap=True,
    )
    avisos_lectura = []
    if resumen["filas_con_error"] or resumen["duplicados"]:
        avisos_lectura.append(
            ft.Text(
                f"Filas del archivo con error: {resumen['filas_con_error']} · CAR duplicados: {resumen['duplicados']}",
                color=ft.Colors.ORANGE_800,
            )
        )
    return ft.Column([tarjetas, *avisos_lectura, ft.Row([estado, filtro_sustento], wrap=True), listado.content],
                     data=listado.data)


# Fase 2: totales por tipo de comprobante y moneda

TIPOS_CP = {"01": "Facturas", "03": "Boletas", "07": "Notas de crédito", "08": "Notas de débito",
            totales.TOTAL: "TOTAL"}


def _fase_totales(resumen: dict, filas: list[dict]) -> ft.Control:
    if resumen["fases"] < 2:
        return _sin_fase()
    tabla = c.tabla(["Tipo", "Moneda", "Cant. SIRE", "Cant. Bizlinks", "Base SIRE", "Base Bizlinks",
                     "IGV SIRE", "IGV Bizlinks", "Total SIRE", "Total Bizlinks", "Diferencia (SIRE − Bizlinks)"])
    for f in filas:
        negrita = ft.FontWeight.BOLD if f["tipo_cp"] == totales.TOTAL else None
        celdas = [TIPOS_CP.get(f["tipo_cp"], f["tipo_cp"]), f["moneda"]] + [
            _monto(f[f"{lado}_{campo}"]) if campo != "cantidad" else f"{f[f'{lado}_{campo}']:,}"
            for campo in ("cantidad", "base", "igv", "total") for lado in ("sire", "biz")
        ]
        tabla.rows.append(
            c.fila(
                *[ft.Text(v, weight=negrita) for v in celdas],
                ft.Text("Cuadra", color=c.COLOR_ESTADO["COINCIDE"], weight=ft.FontWeight.BOLD) if not f["diferencias"]
                else ft.Text(_diferencia_totales(f["diferencias"]), color=c.COLOR_ESTADO["DIFERENCIA"],
                             weight=ft.FontWeight.BOLD),
            )
        )
    con_dif = resumen["totales_con_diferencia"]
    return ft.Column(
        [
            ft.Row(
                [
                    c.tarjeta("Filas que cuadran", len(filas) - con_dif, c.COLOR_ESTADO["COINCIDE"]),
                    c.tarjeta("Filas con diferencia", con_dif, c.COLOR_ESTADO["DIFERENCIA"]),
                ],
                wrap=True,
            ),
            ft.Text(
                f"Suman todos los comprobantes de cada origen. No suman los anulados ni los rechazados por SUNAT "
                f"(SIRE: {resumen['totales_excluidos_sire']}, Bizlinks: {resumen['totales_excluidos_bizlinks']}). "
                "Las notas de crédito restan."
            ),
            ft.Row([tabla], scroll=ft.ScrollMode.AUTO),
        ]
    )


# Fase 3: IGV calculado (base x tasa) frente al declarado

def _fase_igv(page: ft.Page, nav, pool, trabajo, resumen: dict, filas_totales: list[dict], sustentar) -> ft.Control:
    if resumen["fases"] < 3:
        return _sin_fase()
    tasa = resumen["tasa_igv"]
    columnas = ["CAR SUNAT", "Comprobante", "Sustento", "Base SIRE", "IGV SIRE", "IGV calculado SIRE",
                "Base Bizlinks", "IGV Bizlinks", "IGV calculado Bizlinks"]

    def fila(f: dict) -> ft.DataRow:
        def igv_vs_calculado(lado: str) -> ft.Control:
            declarado, calculado = f[f"{lado}_igv"], f[f"{lado}_igv_calculado"]
            if calculado is None:
                return ft.Text("")
            observado = abs(abs(declarado) - calculado) > resumen["tolerancia_igv"]
            return ft.Text(_monto(calculado), color=c.COLOR_ESTADO["DIFERENCIA"] if observado else None,
                           weight=ft.FontWeight.BOLD if observado else None)

        return c.fila(
            c.copiable(page, f["car"]), c.copiable(page, _comprobante(f)), _celda_sustento(f, sustentar),
            _monto(f["sire_base"]), _monto(f["sire_igv"]), igv_vs_calculado("sire"),
            _monto(f["biz_base"]), _monto(f["biz_igv"]), igv_vs_calculado("biz"),
        )

    listado = _listado(page, nav, pool, trabajo, columnas, fila, lambda: {"igv_observado": True},
                       sufijo="_igv_observados")
    total_igv = [f for f in filas_totales if f["tipo_cp"] == totales.TOTAL]
    resumen_igv = [
        ft.Text(
            f"Total {f['moneda']} · IGV SIRE {_monto(f['sire_igv'])} (calculado {_monto(f['sire_igv_calculado'])}) · "
            f"IGV Bizlinks {_monto(f['biz_igv'])} (calculado {_monto(f['biz_igv_calculado'])})",
            weight=ft.FontWeight.BOLD,
        )
        for f in total_igv
    ]
    return ft.Column(
        [
            ft.Row(
                [
                    c.tarjeta("Tasa de IGV", f"{tasa * 100:g}%"),
                    c.tarjeta("Observados en SIRE", resumen["igv_observados_sire"], c.COLOR_ESTADO["DIFERENCIA"]),
                    c.tarjeta("Observados en Bizlinks", resumen["igv_observados_bizlinks"], c.COLOR_ESTADO["DIFERENCIA"]),
                ],
                wrap=True,
            ),
            ft.Text(
                f"IGV calculado = base imponible × {tasa * 100:g}%, redondeado a céntimos. Se observa el comprobante "
                f"cuando el IGV del SIRE o de Bizlinks se aparta del calculado en más de "
                f"{resumen['tolerancia_igv']} (redondeo línea por línea). No aplica a anulados."
            ),
            *resumen_igv,
            listado.content,
        ],
        data=listado.data,
    )


_NOMBRES_TOTALES = {"cantidad": "Cant.", "base": "Base", "igv": "IGV", "total": "Total",
                    "igv_calculado": "IGV calculado"}


def _diferencia_totales(diferencias) -> str:
    """Cant. +1 · Base +361.46 · ...: lo que el SIRE tiene de más (+) o de menos (−) frente a Bizlinks."""
    if isinstance(diferencias, str):
        diferencias = json.loads(diferencias)
    partes = []
    for campo, v in diferencias.items():
        resta = Decimal(v["sire"]) - Decimal(v["bizlinks"])
        texto = f"{resta:+,}" if campo == "cantidad" else f"{resta:+,.2f}"
        partes.append(f"{_NOMBRES_TOTALES.get(campo, campo)} {texto}")
    return " · ".join(partes)


def _sin_fase() -> ft.Control:
    return ft.Text(
        "Esta comparación se hizo antes de agregar las fases 2 y 3. Encole de nuevo el archivo para obtenerlas.",
        color=ft.Colors.ORANGE_800,
    )


@dataclass
class _Listado:
    content: ft.Control
    data: Callable  # async (reiniciar=False): carga la página actual


def _listado(page: ft.Page, nav, pool, trabajo, columnas: list[str], armar_fila, filtros: Callable[[], dict],
             sufijo: str = "") -> _Listado:
    """Tabla paginada del detalle con descarga CSV/Excel de lo filtrado.
    filtros() devuelve estado / igv_observado / sustento para repo.detalle y repo.contar."""
    tabla = c.tabla(columnas)
    pagina = {"n": 0, "total": 0}
    info = ft.Text()

    async def cargar(reiniciar: bool = False):
        if reiniciar:
            pagina["n"] = 0
        f = {"estado": None, **filtros()}
        async with pool.connection() as conn:
            pagina["total"] = await repo.contar(conn, trabajo.id, **f)
            filas = await repo.detalle(conn, trabajo.id, limite=POR_PAGINA, desplazamiento=pagina["n"] * POR_PAGINA, **f)
        tabla.rows = [armar_fila(f) for f in filas]
        paginas = max(1, -(-pagina["total"] // POR_PAGINA))
        info.value = f"Página {pagina['n'] + 1} de {paginas} · {pagina['total']} comprobantes"
        page.update()

    async def mover(delta: int):
        nueva = pagina["n"] + delta
        if 0 <= nueva * POR_PAGINA < max(pagina["total"], 1):
            pagina["n"] = nueva
            await cargar()

    async def descargar(formato: str):
        async with pool.connection() as conn:
            filas = await repo.detalle(conn, trabajo.id, limite=None, **{"estado": None, **filtros()})
        valores = [[_celda(f[col]) for col in repo.COLUMNAS_EXPORTAR] for f in filas]
        convertir = exportar.a_xlsx if formato == "xlsx" else exportar.a_csv
        contenido = await asyncio.to_thread(convertir, repo.COLUMNAS_EXPORTAR, valores)
        await nav.picker.save_file(
            file_name=f"comparacion_{trabajo.empresa_ruc}_{trabajo.periodo}_{trabajo.id}{sufijo}.{formato}",
            src_bytes=contenido,
        )

    contenido = ft.Column(
        [
            ft.Row(
                [
                    ft.OutlinedButton("CSV", icon=ft.Icons.DOWNLOAD, on_click=lambda _: page.run_task(descargar, "csv")),
                    ft.OutlinedButton("Excel", icon=ft.Icons.DOWNLOAD, on_click=lambda _: page.run_task(descargar, "xlsx")),
                ],
                wrap=True,
            ),
            ft.Row([tabla], scroll=ft.ScrollMode.AUTO),
            ft.Row(
                [
                    ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda _: page.run_task(mover, -1)),
                    info,
                    ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda _: page.run_task(mover, 1)),
                ]
            ),
        ]
    )
    return _Listado(contenido, cargar)


def _texto_diferencias(diferencias) -> str:
    if not diferencias:
        return ""
    if isinstance(diferencias, str):
        diferencias = json.loads(diferencias)
    return "; ".join(f"{campo}: {v['sire']} ≠ {v['bizlinks']}" for campo, v in diferencias.items())


def _comprobante(f: dict) -> str:
    """F001-00000001: el formato de serienumero en Bizlinks y en los portales de SUNAT."""
    return f"{f['serie']}-{f['numero']:08d}"


def _total(total, anulado: bool) -> str:
    if total is None:
        return ""
    return f"{total} (anulado)" if anulado else str(total)


def _celda(valor):
    if isinstance(valor, dict):
        return _texto_diferencias(valor)
    return valor


def _monto(valor) -> str:
    return "" if valor is None else f"{valor:,.2f}"
