"""Lectura de comprobantes desde la BD de Bizlinks (solo lectura)."""

from datetime import date
from functools import cache
from pathlib import Path

from app.nucleo import estados_ose
from app.nucleo.db import conexion
from app.nucleo.modelos import Comprobante
from app.nucleo.sire import normalizador as n

_CONSULTA = Path(__file__).parent / "consultas" / "bizlinks_comprobantes.sql"


@cache
def _sql() -> str:
    return _CONSULTA.read_text(encoding="utf-8")


def rango_periodo(periodo: str) -> tuple[date, date]:
    """'202609' -> (2026-09-01, 2026-10-01)."""
    anio, mes = int(periodo[:4]), int(periodo[4:])
    desde = date(anio, mes, 1)
    hasta = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return desde, hasta


async def listar(ruc: str, periodo: str) -> list[Comprobante]:
    desde, hasta = rango_periodo(periodo)
    pool = await conexion.bizlinks()
    async with pool.connection() as conn:
        # fechaemision es varchar AAAA-MM-DD en Bizlinks: se compara como texto
        cur = await conn.execute(_sql(), {"ruc": ruc, "desde": desde.isoformat(), "hasta": hasta.isoformat()})
        filas = await cur.fetchall()
    return [_a_comprobante(f) for f in filas]


def _a_comprobante(f: dict) -> Comprobante:
    estado = estados_ose.normalizar(f.get("estado_ose"))
    return Comprobante(
        ruc=n.ruc(f["ruc"]),
        tipo_cp=n.tipo_cp(f["tipo_cp"]),
        serie=n.serie(f["serie"]),
        numero=n.numero(f["numero"]),
        fecha_emision=n.fecha(f["fecha_emision"]),
        moneda=n.moneda(f["moneda"]),
        base_imponible=n.monto(f["base_imponible"]),
        igv=n.monto(f["igv"]),
        total=n.monto(f["total"]),
        doc_receptor=n.documento(f["doc_receptor"]),
        # Dado de baja (AN_04): como en el SIRE, solo se valida que exista
        anulado=estados_ose.categoria(estado) == estados_ose.ANULADO,
        estado_ose=estado,
        mensaje_sunat=n.documento(f.get("mensaje_sunat")),
    )
