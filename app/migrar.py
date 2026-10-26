"""Aplica los scripts sql/*.sql pendientes en la BD de historial, en orden y una sola vez.

    python -m app.migrar            aplica lo pendiente
    python -m app.migrar --estado   solo lista aplicadas y pendientes

Cada script corre en su propia transacción y se registra en public.migracion_aplicada.
"""

import hashlib
import sys
from pathlib import Path

import psycopg

from app import config

CARPETA = Path(__file__).resolve().parent.parent / "sql"

_TABLA = """
CREATE TABLE IF NOT EXISTS public.migracion_aplicada (
    nombre      varchar(200) PRIMARY KEY,
    hash        char(64)     NOT NULL,
    aplicada_en timestamptz  NOT NULL DEFAULT now()
)
"""


def _scripts() -> list[Path]:
    return sorted(CARPETA.glob("*.sql"))


def main(solo_estado: bool) -> int:
    with psycopg.connect(config.cargar().hist_dsn, autocommit=True) as conn:
        conn.execute(_TABLA)
        aplicadas = {f: h for f, h in conn.execute("SELECT nombre, hash FROM public.migracion_aplicada")}
        pendientes = []
        for script in _scripts():
            contenido = script.read_text(encoding="utf-8")
            h = hashlib.sha256(contenido.encode()).hexdigest()
            if script.name not in aplicadas:
                pendientes.append((script, contenido, h))
            elif aplicadas[script.name] != h:
                print(f"AVISO: {script.name} cambió después de aplicarse; no se vuelve a ejecutar")

        print(f"Aplicadas: {len(aplicadas)} · Pendientes: {len(pendientes)}")
        if solo_estado:
            for script, _, _ in pendientes:
                print(f"  pendiente {script.name}")
            return 0

        for script, contenido, h in pendientes:
            print(f"Aplicando {script.name} ...", end=" ", flush=True)
            with conn.transaction():
                # Sin parámetros psycopg envía el script completo (varias sentencias, bloques DO)
                conn.execute(contenido)
                conn.execute("INSERT INTO public.migracion_aplicada (nombre, hash) VALUES (%s, %s)", (script.name, h))
            print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(solo_estado="--estado" in sys.argv))
