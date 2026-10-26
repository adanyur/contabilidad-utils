"""Configuración leída de variables de entorno."""

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import cache


@dataclass(frozen=True)
class Config:
    hist_dsn: str
    bizlinks_dsn: str
    tolerancia: Decimal
    tasa_igv: Decimal
    tolerancia_igv: Decimal
    worker_vt: int
    max_intentos: int
    max_archivo_mb: int
    log_level: str


def _obligatoria(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


@cache
def cargar() -> Config:
    return Config(
        hist_dsn=_obligatoria("HIST_DSN"),
        bizlinks_dsn=_obligatoria("BIZLINKS_DSN"),
        tolerancia=Decimal(os.environ.get("TOLERANCIA", "0.01")),
        tasa_igv=Decimal(os.environ.get("TASA_IGV", "0.18")),
        tolerancia_igv=Decimal(os.environ.get("TOLERANCIA_IGV", "0.05")),
        worker_vt=int(os.environ.get("WORKER_VT", "120")),
        max_intentos=int(os.environ.get("MAX_INTENTOS", "3")),
        max_archivo_mb=int(os.environ.get("MAX_ARCHIVO_MB", "50")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )


def configurar_logging(cfg: Config) -> None:
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
