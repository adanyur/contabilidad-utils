"""Persistencia del resultado de la comparación (schema comparacion)."""

import json
from typing import Optional

from psycopg import AsyncConnection

from app.procesos.comparacion import sustento
from app.procesos.comparacion.igv import VerificacionIgv
from app.procesos.comparacion.motor import ResultadoComparacion
from app.procesos.comparacion.parametros import ParametrosFases
from app.procesos.comparacion.totales import ResultadoTotales

_COLUMNAS_DETALLE = (
    "trabajo_id", "car", "tipo_cp", "serie", "numero", "estado",
    "sire_fecha", "sire_moneda", "sire_base", "sire_igv", "sire_total", "sire_doc_receptor", "sire_anulado",
    "biz_fecha", "biz_moneda", "biz_base", "biz_igv", "biz_total", "biz_doc_receptor", "biz_anulado",
    "diferencias", "biz_estado", "biz_mensaje_sunat",
    "sire_igv_calculado", "biz_igv_calculado", "igv_observado", "requiere_sustento",
)

# Columnas que se muestran en pantalla y se exportan (las de sustento vienen de comparacion.sustento)
COLUMNAS_EXPORTAR = (
    "car", "tipo_cp", "serie", "numero", "estado",
    "sire_fecha", "sire_moneda", "sire_base", "sire_igv", "sire_igv_calculado", "sire_total", "sire_anulado",
    "biz_fecha", "biz_moneda", "biz_base", "biz_igv", "biz_igv_calculado", "biz_total", "biz_anulado",
    "biz_estado", "biz_mensaje_sunat", "diferencias", "igv_observado",
    "requiere_sustento", "sustento_estado", "sustento_motivo", "sustento_comentario", "sustento_usuario",
)
_SUSTENTO = {"sustento_estado": "s.estado", "sustento_motivo": "s.motivo", "sustento_comentario": "s.comentario",
             "sustento_usuario": "s.usuario"}

# Filtro de sustento en pantalla: PENDIENTES = los que impiden cerrar el periodo
FILTROS_SUSTENTO = {
    "REQUIERE": "d.requiere_sustento",
    "PENDIENTES": "d.requiere_sustento AND coalesce(s.estado, 'PENDIENTE') <> 'SUSTENTADO'",
    "PENDIENTE": "d.requiere_sustento AND coalesce(s.estado, 'PENDIENTE') = 'PENDIENTE'",
    "EN_CORRECCION": "s.estado = 'EN_CORRECCION'",
    "SUSTENTADO": "s.estado = 'SUSTENTADO'",
}

_COLUMNAS_TOTALES = (
    "tipo_cp", "moneda",
    "sire_cantidad", "sire_base", "sire_igv", "sire_total", "sire_igv_calculado",
    "biz_cantidad", "biz_base", "biz_igv", "biz_total", "biz_igv_calculado",
    "diferencias",
)


def _lado(c) -> tuple:
    if c is None:
        return (None,) * 6 + (False,)
    return (c.fecha_emision, c.moneda, c.base_imponible, c.igv, c.total, c.doc_receptor, c.anulado)


def _acumulado(a) -> tuple:
    return (a.cantidad, a.base, a.igv, a.total, a.igv_calculado)


async def guardar(
    conn: AsyncConnection,
    trabajo_id: int,
    resultado: ResultadoComparacion,
    filas_con_error: int,
    totales: ResultadoTotales,
    verificacion: dict[str, VerificacionIgv],
    parametros: ParametrosFases,
) -> None:
    """Reemplaza el resultado de las tres fases (idempotente ante reintentos). Debe ir en una transacción."""
    for tabla in ("detalle", "totales", "resumen"):
        await conn.execute(f"DELETE FROM comparacion.{tabla} WHERE trabajo_id = %s", (trabajo_id,))

    cur = conn.cursor()
    async with cur.copy(f"COPY comparacion.detalle ({', '.join(_COLUMNAS_DETALLE)}) FROM STDIN") as copy:
        for d in resultado.detalles:
            c = d.sire or d.bizlinks
            v = verificacion[d.llave]
            await copy.write_row(
                (trabajo_id, d.llave, c.tipo_cp, c.serie, c.numero, d.estado)
                + _lado(d.sire)
                + _lado(d.bizlinks)
                + (json.dumps(d.diferencias) if d.diferencias else None,)
                + ((d.bizlinks.estado_ose, d.bizlinks.mensaje_sunat) if d.bizlinks else (None, None))
                + (v.sire_calculado, v.biz_calculado, v.observado, sustento.requiere(d, v))
            )

    filas_totales = [(f, f.diferencias(parametros.tolerancia)) for f in totales.filas]
    async with cur.copy(f"COPY comparacion.totales (trabajo_id, {', '.join(_COLUMNAS_TOTALES)}) FROM STDIN") as copy:
        for f, dif in filas_totales:
            await copy.write_row(
                (trabajo_id, f.tipo_cp, f.moneda) + _acumulado(f.sire) + _acumulado(f.bizlinks)
                + (json.dumps(dif) if dif else None,)
            )

    r = resultado.resumen
    await conn.execute(
        """
        INSERT INTO comparacion.resumen
            (trabajo_id, total_sire, total_bizlinks, coinciden, con_diferencia, solo_sire, solo_bizlinks,
             filas_con_error, duplicados, solo_bizlinks_rechazados, solo_bizlinks_pendientes,
             fases, tasa_igv, tolerancia_igv, igv_observados_sire, igv_observados_bizlinks,
             totales_excluidos_sire, totales_excluidos_bizlinks, totales_con_diferencia)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 3, %s, %s, %s, %s, %s, %s, %s)
        """,
        (trabajo_id, resultado.total_sire, resultado.total_bizlinks, r["COINCIDE"], r["DIFERENCIA"],
         r["SOLO_SIRE"], r["SOLO_BIZLINKS"], filas_con_error,
         len(resultado.duplicados_sire) + len(resultado.duplicados_bizlinks),
         resultado.solo_bizlinks_rechazados, resultado.solo_bizlinks_pendientes,
         parametros.tasa_igv, parametros.tolerancia_igv,
         sum(v.sire_observado for v in verificacion.values()), sum(v.biz_observado for v in verificacion.values()),
         totales.excluidos_sire, totales.excluidos_bizlinks, sum(1 for _, dif in filas_totales if dif)),
    )


async def totales(conn: AsyncConnection, trabajo_id: int) -> list[dict]:
    cur = await conn.execute(
        f"SELECT {', '.join(_COLUMNAS_TOTALES)} FROM comparacion.totales WHERE trabajo_id = %s "
        "ORDER BY moneda, tipo_cp = 'TOTAL', tipo_cp",
        (trabajo_id,),
    )
    return await cur.fetchall()


async def resumen(conn: AsyncConnection, trabajo_id: int) -> Optional[dict]:
    cur = await conn.execute("SELECT * FROM comparacion.resumen WHERE trabajo_id = %s", (trabajo_id,))
    return await cur.fetchone()


# El sustento se busca por el periodo (empresa + periodo) del trabajo y el CAR
_DESDE = """
  FROM comparacion.detalle d
  JOIN nucleo.trabajo t ON t.id = d.trabajo_id
  LEFT JOIN comparacion.periodo p ON p.empresa_id = t.empresa_id AND p.periodo = t.periodo
  LEFT JOIN comparacion.sustento s ON s.periodo_id = p.id AND s.car = d.car
"""


def _filtro(trabajo_id: int, estado: Optional[str], igv_observado: bool, sustento: Optional[str]) -> tuple[str, list]:
    sql, params = " WHERE d.trabajo_id = %s", [trabajo_id]
    if estado:
        sql += " AND d.estado = %s"
        params.append(estado)
    if igv_observado:
        sql += " AND d.igv_observado"
    if sustento:
        sql += f" AND {FILTROS_SUSTENTO[sustento]}"
    return sql, params


async def detalle(
    conn: AsyncConnection, trabajo_id: int, estado: Optional[str], limite: Optional[int], desplazamiento: int = 0,
    igv_observado: bool = False, sustento: Optional[str] = None,
) -> list[dict]:
    """igv_observado=True deja solo los observados en la fase 3; sustento filtra por FILTROS_SUSTENTO."""
    filtro, params = _filtro(trabajo_id, estado, igv_observado, sustento)
    columnas = ", ".join(f"{_SUSTENTO[c]} AS {c}" if c in _SUSTENTO else f"d.{c}" for c in COLUMNAS_EXPORTAR)
    sql = f"SELECT {columnas}, p.id AS periodo_id{_DESDE}{filtro} ORDER BY d.car"
    if limite is not None:
        sql += " LIMIT %s OFFSET %s"
        params += [limite, desplazamiento]
    cur = await conn.execute(sql, params)
    return await cur.fetchall()


async def contar(conn: AsyncConnection, trabajo_id: int, estado: Optional[str], igv_observado: bool = False,
                 sustento: Optional[str] = None) -> int:
    filtro, params = _filtro(trabajo_id, estado, igv_observado, sustento)
    cur = await conn.execute(f"SELECT count(*) AS n{_DESDE}{filtro}", params)
    return (await cur.fetchone())["n"]


async def historial_comprobante(
    conn: AsyncConnection, empresa_id: int, serie: Optional[str] = None, numero: Optional[int] = None,
    car: Optional[str] = None,
) -> list[dict]:
    """Estado de un comprobante (por CAR, o por serie y número) en la carga vigente de cada periodo,
    con su sustento; del más reciente al más antiguo."""
    filtro, params = ("d.car = %s", [car]) if car else ("d.serie = %s AND d.numero = %s", [serie, numero])
    cur = await conn.execute(
        f"""
        SELECT t.id AS trabajo_id, t.periodo, t.finalizado_en, d.car, d.tipo_cp, d.serie, d.numero,
               d.estado, d.diferencias, d.requiere_sustento, s.estado AS sustento_estado
        {_DESDE}
         WHERE t.empresa_id = %s AND t.estado = 'OK' AND {filtro}
         ORDER BY t.finalizado_en DESC
        """,
        [empresa_id, *params],
    )
    return await cur.fetchall()
