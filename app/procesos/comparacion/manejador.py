"""Ejecución de una comparación dentro del worker, en tres fases:
1. comprobante por comprobante, 2. totales por tipo y moneda, 3. IGV calculado vs declarado."""

import asyncio

from app.nucleo.db import bizlinks_repo, carga_repo, conexion, empresa_repo
from app.nucleo.modelos import Trabajo
from app.nucleo.sire import lector
from app.procesos.base import Contexto
from app.procesos.comparacion import igv, motor, periodo_repo, repo, totales
from app.procesos.comparacion.parametros import ParametrosFases


async def ejecutar(trabajo: Trabajo, ctx: Contexto) -> str:
    pool = await conexion.historial()
    async with pool.connection() as conn:
        empresa = await empresa_repo.obtener(conn, trabajo.empresa_id)
        carga = await carga_repo.obtener(conn, trabajo.carga_archivo_id)
        cabecera = await periodo_repo.obtener(conn, trabajo.empresa_id, trabajo.periodo)
    if empresa is None or carga is None:
        raise ValueError("La empresa o el archivo del trabajo ya no existen")
    if cabecera and cabecera["estado"] == periodo_repo.CERRADO:
        raise ValueError(f"El periodo {trabajo.periodo} está cerrado; reábralo para volver a cargar")

    await ctx.avance(10, "Leyendo archivo SIRE y comprobantes de Bizlinks")
    # El archivo se procesa en un hilo mientras la consulta a Bizlinks corre en el event loop
    lectura, comprobantes_biz = await asyncio.gather(
        asyncio.to_thread(
            lector.leer_rvie, bytes(carga["contenido"]), carga["nombre_archivo"], empresa["ruc"], trabajo.periodo
        ),
        bizlinks_repo.listar(empresa["ruc"], trabajo.periodo),
    )
    if not lectura.comprobantes:
        detalle = f" Primer error: {lectura.errores[0]}" if lectura.errores else ""
        raise ValueError(f"El archivo SIRE no tiene comprobantes válidos.{detalle}")

    p = ParametrosFases.desde_trabajo(trabajo.parametros)
    await ctx.avance(40, f"Fase 1: comparando {len(lectura.comprobantes)} del SIRE con {len(comprobantes_biz)} de Bizlinks")
    resultado = await asyncio.to_thread(motor.comparar, lectura.comprobantes, comprobantes_biz, p.tolerancia)

    await ctx.avance(55, "Fase 2: comparando totales por tipo de comprobante")
    resultado_totales = await asyncio.to_thread(totales.calcular, lectura.comprobantes, comprobantes_biz, p.tasa_igv)

    await ctx.avance(65, f"Fase 3: verificando IGV al {p.tasa_igv * 100:g}%")
    verificacion = await asyncio.to_thread(igv.verificar, resultado.detalles, p.tasa_igv, p.tolerancia_igv)

    await ctx.avance(75, "Guardando resultado")
    async with pool.connection() as conn:
        async with conn.transaction():
            await repo.guardar(
                conn, trabajo.id, resultado, len(lectura.errores), resultado_totales, verificacion, p
            )
            # Pasa a ser la carga vigente del periodo; se borra el detalle de las anteriores
            await periodo_repo.registrar_carga(conn, trabajo.empresa_id, trabajo.periodo, trabajo.id)

    r = resultado.resumen
    mensaje = (
        f"Coinciden {r['COINCIDE']}, con diferencia {r['DIFERENCIA']}, "
        f"solo SIRE {r['SOLO_SIRE']}, solo Bizlinks {r['SOLO_BIZLINKS']}"
    )
    detalle_biz = []
    if resultado.solo_bizlinks_rechazados:
        detalle_biz.append(f"{resultado.solo_bizlinks_rechazados} rechazados por SUNAT")
    if resultado.solo_bizlinks_pendientes:
        detalle_biz.append(f"{resultado.solo_bizlinks_pendientes} sin respuesta de SUNAT")
    if detalle_biz:
        mensaje += f" ({', '.join(detalle_biz)})"
    totales_dif = sum(1 for f in resultado_totales.filas if f.diferencias(p.tolerancia))
    mensaje += f". Totales: {'cuadran' if not totales_dif else f'{totales_dif} filas con diferencia'}"
    igv_obs = sum(1 for v in verificacion.values() if v.observado)
    mensaje += f". IGV: {'sin observaciones' if not igv_obs else f'{igv_obs} comprobantes observados'}"
    if lectura.errores:
        mensaje += f". {len(lectura.errores)} filas del archivo con error"
    return mensaje
