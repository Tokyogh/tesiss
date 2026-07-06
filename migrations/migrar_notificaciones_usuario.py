from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


def find_db_path() -> str:
    if len(sys.argv) > 2:
        print("Uso: python migrar_notificaciones_usuario.py [ruta/a/vinova.db]")
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


DB_PATH = find_db_path()


def backup_db(path: str) -> str:
    backup_path = f"{path}.backup_notificaciones_usuario_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(path, backup_path)
    return backup_path


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return cur.fetchone() is not None


def column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    if not table_exists(cur, table):
        return False
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_column_if_missing(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    if not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"No encontré la base de datos: {DB_PATH}")
        sys.exit(1)

    backup_path = backup_db(DB_PATH)
    print(f"Respaldo creado: {backup_path}")

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notificaciones_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                remitente_id INTEGER,
                tipo TEXT DEFAULT 'mensaje',
                prioridad TEXT DEFAULT 'normal',
                titulo TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                leida INTEGER DEFAULT 0,
                eliminado_usuario INTEGER DEFAULT 0,
                creado_en TEXT NOT NULL,
                leida_en TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (remitente_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
        """)

        columnas = {
            "remitente_id": "INTEGER",
            "tipo": "TEXT DEFAULT 'mensaje'",
            "prioridad": "TEXT DEFAULT 'normal'",
            "leida": "INTEGER DEFAULT 0",
            "eliminado_usuario": "INTEGER DEFAULT 0",
            "creado_en": "TEXT",
            "leida_en": "TEXT",
        }

        for columna, definicion in columnas.items():
            add_column_if_missing(cur, "notificaciones_usuario", columna, definicion)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario_destino
            ON notificaciones_usuario(usuario_id, eliminado_usuario, leida, creado_en)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario_remitente
            ON notificaciones_usuario(remitente_id, creado_en)
        """)

        con.commit()
        print("Migración de notificaciones internas aplicada correctamente.")

    except Exception:
        con.rollback()
        print("Error aplicando migración. Revisa el respaldo generado antes de reintentar.")
        raise

    finally:
        con.close()


if __name__ == "__main__":
    main()
