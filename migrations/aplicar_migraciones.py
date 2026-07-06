from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime


SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


def find_db_path() -> str:
    if len(sys.argv) > 2:
        print("Uso: python aplicar_migraciones.py [ruta/a/vinova.db]")
        sys.exit(1)

    if len(sys.argv) == 2:
        return os.path.abspath(sys.argv[1])

    candidates = [
        os.path.join(os.getcwd(), "vinova.db"),
        os.path.join(SCRIPT_DIR, "vinova.db"),
        os.path.join(os.path.dirname(SCRIPT_DIR), "vinova.db"),
    ]

    for start in {os.getcwd(), SCRIPT_DIR, os.path.dirname(SCRIPT_DIR)}:
        current = os.path.abspath(start)
        while True:
            candidates.append(os.path.join(current, "vinova.db"))
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent

    seen = set()
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.exists(candidate):
            return candidate

    return os.path.abspath(os.path.join(os.getcwd(), "vinova.db"))


def find_migrations_dir(db_path: str) -> str:
    candidates = [
        SCRIPT_DIR,
        os.path.join(os.getcwd(), "migrations"),
        os.path.join(os.path.dirname(db_path), "migrations"),
    ]

    for candidate in candidates:
        if os.path.exists(os.path.join(candidate, "migrar_stock_concesionarias_articulos.py")):
            return os.path.abspath(candidate)

    return SCRIPT_DIR


DB_PATH = find_db_path()
BASE_DIR = os.path.dirname(DB_PATH)
MIGRATIONS_DIR = find_migrations_dir(DB_PATH)


MIGRACIONES = [
    ("20260703_establecimientos", "migrar_establecimientos.py", "py"),
    ("20260705_articulos_inventario", "20260705_articulos_inventario.sql", "sql"),
    ("20260706_stock_concesionarias_articulos", "migrar_stock_concesionarias_articulos.py", "py"),
    ("20260706_auditoria_acciones", "migrar_auditoria_acciones.py", "py"),
    ("20260706_notificaciones_usuario", "migrar_notificaciones_usuario.py", "py"),
]


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def preparar_tabla_migraciones(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            archivo TEXT NOT NULL,
            tipo TEXT NOT NULL,
            aplicado_en TEXT NOT NULL
        )
    """)
    con.commit()


def migracion_aplicada(con: sqlite3.Connection, version: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ? LIMIT 1",
        (version,),
    ).fetchone()
    return row is not None


def marcar_aplicada(con: sqlite3.Connection, version: str, archivo: str, tipo: str) -> None:
    con.execute("""
        INSERT OR REPLACE INTO schema_migrations (version, archivo, tipo, aplicado_en)
        VALUES (?, ?, ?, ?)
    """, (version, archivo, tipo, ahora()))
    con.commit()


def aplicar_sql(con: sqlite3.Connection, archivo: str) -> None:
    path = os.path.join(MIGRATIONS_DIR, archivo)
    with open(path, "r", encoding="utf-8") as handle:
        con.executescript(handle.read())
    con.commit()


def aplicar_py(archivo: str) -> None:
    path = os.path.join(MIGRATIONS_DIR, archivo)
    subprocess.run([sys.executable, path, DB_PATH], check=True, cwd=BASE_DIR)


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"No encontré la base de datos: {DB_PATH}")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)
    try:
        preparar_tabla_migraciones(con)

        pendientes = 0
        for version, archivo, tipo in MIGRACIONES:
            if migracion_aplicada(con, version):
                print(f"Saltada: {version} ({archivo})", flush=True)
                continue

            print(f"Aplicando: {version} ({archivo})", flush=True)
            if tipo == "sql":
                aplicar_sql(con, archivo)
            elif tipo == "py":
                aplicar_py(archivo)
            else:
                raise ValueError(f"Tipo de migración no soportado: {tipo}")

            marcar_aplicada(con, version, archivo, tipo)
            pendientes += 1

        print(f"Migraciones aplicadas: {pendientes}", flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()
