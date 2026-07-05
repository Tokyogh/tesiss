"""
Migración VINOVA: crea la tabla de auditoría de acciones.

Uso:
    python migrar_auditoria_acciones.py
    python migrar_auditoria_acciones.py ruta/a/vinova.db

Por defecto busca vinova.db en la misma carpeta desde donde ejecutes el comando.
La migración es idempotente: puedes ejecutarla más de una vez sin duplicar la tabla ni los índices.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


MIGRATION_NAME = "001_auditoria_acciones"

SQL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS auditoria_acciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        usuario_rol TEXT,
        accion TEXT NOT NULL,
        entidad TEXT,
        entidad_id INTEGER,
        detalle TEXT,
        ip TEXT,
        user_agent TEXT,
        creado_en TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auditoria_creado_en
        ON auditoria_acciones(creado_en)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auditoria_usuario
        ON auditoria_acciones(usuario_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auditoria_entidad
        ON auditoria_acciones(entidad, entidad_id)
    """,
]


def get_db_path() -> Path:
    if len(sys.argv) > 2:
        raise SystemExit("Uso: python migrar_auditoria_acciones.py [ruta/a/vinova.db]")

    return Path(sys.argv[1] if len(sys.argv) == 2 else "vinova.db").expanduser().resolve()


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def main() -> None:
    db_path = get_db_path()

    if not db_path.exists():
        raise SystemExit(f"No se encontró la base de datos: {db_path}")

    try:
        with sqlite3.connect(db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("BEGIN")

            for statement in SQL_STATEMENTS:
                cursor.execute(statement)

            if not table_exists(cursor, "auditoria_acciones"):
                raise RuntimeError("La tabla auditoria_acciones no fue creada correctamente.")

            connection.commit()

        print(f"Migración aplicada correctamente: {MIGRATION_NAME}")
        print(f"Base de datos: {db_path}")

    except Exception as exc:
        raise SystemExit(f"Error aplicando la migración {MIGRATION_NAME}: {exc}") from exc


if __name__ == "__main__":
    main()
