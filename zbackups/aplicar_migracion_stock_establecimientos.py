

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def find_project_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "vinova.db").exists():
            return candidate
    raise SystemExit("No encontré vinova.db. Ejecuta este script desde la raíz del proyecto.")


def backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"vinova_backup_stock_establecimientos_{stamp}.db")
    shutil.copy2(db_path, backup)
    return backup


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def add_column_if_missing(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in table_columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"Columna creada: {table}.{column}")


def main() -> None:
    root = find_project_root()
    db_path = root / "vinova.db"
    print("Raíz del proyecto:", root)
    print("Base de datos:", db_path.name)
    print("-" * 62)

    backup = backup_db(db_path)
    print("Respaldo creado:", backup.name)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    try:
        con.execute("PRAGMA foreign_keys = ON")

        # Asegura tablas base del módulo de artículos por si el entorno no tenía la migración previa.
        con.execute("""
            CREATE TABLE IF NOT EXISTS articulos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_articulo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'Otros',
                marca TEXT DEFAULT '',
                proveedor TEXT DEFAULT '',
                descripcion TEXT DEFAULT '',
                imagen TEXT DEFAULT '',
                precio REAL NOT NULL DEFAULT 0,
                costo REAL DEFAULT 0,
                stock REAL NOT NULL DEFAULT 0,
                stock_minimo REAL DEFAULT 0,
                unidad TEXT DEFAULT 'Unidad',
                estado TEXT DEFAULT 'Disponible',
                activo INTEGER NOT NULL DEFAULT 1,
                unidades_vendidas REAL NOT NULL DEFAULT 0,
                archivado INTEGER NOT NULL DEFAULT 0,
                archivado_en TEXT,
                archivado_por INTEGER,
                motivo_archivado TEXT,
                creado_por INTEGER,
                actualizado_por INTEGER,
                creado_en TEXT,
                actualizado_en TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS articulo_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                articulo_id INTEGER NOT NULL,
                tipo_movimiento TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 0,
                stock_anterior REAL NOT NULL DEFAULT 0,
                stock_nuevo REAL NOT NULL DEFAULT 0,
                referencia_tipo TEXT DEFAULT '',
                referencia_id INTEGER,
                descripcion TEXT DEFAULT '',
                creado_por INTEGER,
                creado_en TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS factura_articulos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id INTEGER NOT NULL,
                articulo_id INTEGER,
                codigo_articulo TEXT DEFAULT '',
                nombre_articulo TEXT NOT NULL,
                categoria TEXT DEFAULT '',
                cantidad REAL NOT NULL DEFAULT 1,
                unidad TEXT DEFAULT 'Unidad',
                precio_unitario REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                creado_en TEXT
            )
        """)

        # Columnas de relación y datos faltantes.
        add_column_if_missing(con, "vehiculos", "placa", "TEXT")
        add_column_if_missing(con, "usuarios", "establecimiento_id", "INTEGER")
        add_column_if_missing(con, "mantenimientos", "establecimiento_id", "INTEGER")
        add_column_if_missing(con, "facturas_vehiculo", "establecimiento_id", "INTEGER")
        add_column_if_missing(con, "factura_articulos", "establecimiento_id", "INTEGER")
        add_column_if_missing(con, "articulo_movimientos", "establecimiento_id", "INTEGER")

        con.execute("""
            CREATE TABLE IF NOT EXISTS articulo_stock_establecimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                articulo_id INTEGER NOT NULL,
                establecimiento_id INTEGER NOT NULL,
                stock REAL NOT NULL DEFAULT 0,
                stock_minimo REAL NOT NULL DEFAULT 0,
                unidades_vendidas REAL NOT NULL DEFAULT 0,
                creado_en TEXT NOT NULL,
                actualizado_en TEXT NOT NULL,
                UNIQUE(articulo_id, establecimiento_id),
                FOREIGN KEY (articulo_id) REFERENCES articulos(id) ON DELETE CASCADE,
                FOREIGN KEY (establecimiento_id) REFERENCES establecimientos(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_articulo_stock_est_articulo ON articulo_stock_establecimiento(articulo_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articulo_stock_est_establecimiento ON articulo_stock_establecimiento(establecimiento_id)")

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Sincroniza trabajadores/usuarios con establecimiento por nombre.
        con.execute("""
            UPDATE usuarios
            SET establecimiento_id = (
                SELECT establecimientos.id
                FROM establecimientos
                WHERE LOWER(TRIM(establecimientos.nombre)) = LOWER(TRIM(usuarios.establecimiento))
                LIMIT 1
            )
            WHERE COALESCE(establecimiento_id, 0) = 0
              AND TRIM(COALESCE(establecimiento, '')) != ''
              AND EXISTS (
                SELECT 1 FROM establecimientos
                WHERE LOWER(TRIM(establecimientos.nombre)) = LOWER(TRIM(usuarios.establecimiento))
              )
        """)

        # Selecciona una sede inicial para migrar el stock global anterior.
        row = con.execute("""
            SELECT id
            FROM establecimientos
            WHERE COALESCE(activo, 1) = 1
            ORDER BY COALESCE(distancia_km, 999999), nombre
            LIMIT 1
        """).fetchone()
        establecimiento_default = row["id"] if row else None

        if establecimiento_default:
            articulos = con.execute("""
                SELECT id, COALESCE(stock, 0) AS stock, COALESCE(stock_minimo, 0) AS stock_minimo,
                       COALESCE(unidades_vendidas, 0) AS unidades_vendidas
                FROM articulos
            """).fetchall()
            for articulo in articulos:
                existe = con.execute("""
                    SELECT 1
                    FROM articulo_stock_establecimiento
                    WHERE articulo_id = ?
                    LIMIT 1
                """, (articulo["id"],)).fetchone()
                if existe:
                    continue
                con.execute("""
                    INSERT INTO articulo_stock_establecimiento (
                        articulo_id, establecimiento_id, stock, stock_minimo, unidades_vendidas, creado_en, actualizado_en
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    articulo["id"],
                    establecimiento_default,
                    articulo["stock"],
                    articulo["stock_minimo"],
                    articulo["unidades_vendidas"],
                    ahora,
                    ahora,
                ))
            print("Stock global migrado a establecimiento inicial.")
        else:
            print("Aviso: no hay establecimientos activos. Crea uno para separar stock por sede.")

        con.commit()
        print("Tablas/columnas verificadas correctamente.")

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print("-" * 62)
    print("Migración aplicada. Reinicia Flask con: python app.py")


if __name__ == "__main__":
    main()
