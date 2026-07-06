from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime


SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


def find_db_path() -> str:
    if len(sys.argv) > 2:
        print("Uso: python migrar_stock_concesionarias_articulos.py [ruta/a/vinova.db]")
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


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    if not table_exists(cur, table):
        return set()
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def add_column_if_missing(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    if table_exists(cur, table) and column not in table_columns(cur, table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"Columna creada: {table}.{column}")


def backup_db(db_path: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.dirname(db_path)
    backup_path = os.path.join(folder, f"vinova_backup_stock_concesionarias_{stamp}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path


def crear_tablas_base(cur: sqlite3.Cursor) -> None:
    cur.execute("""
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
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY (actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY (archivado_por) REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
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
            creado_en TEXT NOT NULL,
            FOREIGN KEY (articulo_id) REFERENCES articulos(id) ON DELETE CASCADE,
            FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
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
            creado_en TEXT NOT NULL,
            FOREIGN KEY (factura_id) REFERENCES facturas_vehiculo(id) ON DELETE CASCADE,
            FOREIGN KEY (articulo_id) REFERENCES articulos(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
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

    cur.execute("CREATE INDEX IF NOT EXISTS idx_articulos_estado ON articulos(activo, archivado, categoria)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articulos_nombre ON articulos(nombre, codigo_articulo, marca)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articulo_movimientos_articulo ON articulo_movimientos(articulo_id, creado_en)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_articulos_factura ON factura_articulos(factura_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articulo_stock_est_articulo ON articulo_stock_establecimiento(articulo_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articulo_stock_est_establecimiento ON articulo_stock_establecimiento(establecimiento_id)")


def concesionarias_activas(cur: sqlite3.Cursor) -> list[sqlite3.Row]:
    if not table_exists(cur, "establecimientos"):
        return []

    cur.execute("""
        SELECT id, nombre
        FROM establecimientos
        WHERE COALESCE(activo, 1) = 1
          AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
        ORDER BY COALESCE(distancia_km, 999999), nombre COLLATE NOCASE
    """)
    return cur.fetchall()


def migrar_stock_global_a_concesionaria(cur: sqlite3.Cursor, concesionaria_id: int) -> int:
    fecha = ahora()
    migrados = 0

    cur.execute("""
        SELECT id, COALESCE(stock, 0) AS stock, COALESCE(stock_minimo, 0) AS stock_minimo,
               COALESCE(unidades_vendidas, 0) AS unidades_vendidas
        FROM articulos
    """)

    for articulo in cur.fetchall():
        cur.execute("""
            SELECT 1
            FROM articulo_stock_establecimiento AS ase
            INNER JOIN establecimientos AS e
                ON e.id = ase.establecimiento_id
            WHERE ase.articulo_id = ?
              AND COALESCE(e.activo, 1) = 1
              AND LOWER(TRIM(COALESCE(e.tipo, ''))) = 'concesionario'
            LIMIT 1
        """, (articulo["id"],))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO articulo_stock_establecimiento (
                articulo_id, establecimiento_id, stock, stock_minimo,
                unidades_vendidas, creado_en, actualizado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(articulo_id, establecimiento_id)
            DO UPDATE SET
                stock = excluded.stock,
                stock_minimo = excluded.stock_minimo,
                unidades_vendidas = excluded.unidades_vendidas,
                actualizado_en = excluded.actualizado_en
        """, (
            articulo["id"],
            concesionaria_id,
            articulo["stock"],
            articulo["stock_minimo"],
            articulo["unidades_vendidas"],
            fecha,
            fecha,
        ))
        migrados += 1

    return migrados


def recalcular_totales_articulos(cur: sqlite3.Cursor) -> None:
    fecha = ahora()
    cur.execute("SELECT id FROM articulos")
    articulos = cur.fetchall()

    for articulo in articulos:
        cur.execute("""
            SELECT COALESCE(SUM(stock), 0) AS stock_total,
                   COALESCE(SUM(unidades_vendidas), 0) AS vendidas_total,
                   COALESCE(MAX(stock_minimo), 0) AS stock_minimo_ref
            FROM articulo_stock_establecimiento
            WHERE articulo_id = ?
        """, (articulo["id"],))
        total = cur.fetchone()
        stock_total = float(total["stock_total"] or 0)

        cur.execute("""
            UPDATE articulos
            SET stock = ?,
                unidades_vendidas = ?,
                stock_minimo = CASE
                    WHEN COALESCE(stock_minimo, 0) = 0 THEN ?
                    ELSE stock_minimo
                END,
                estado = CASE
                    WHEN ? <= 0 AND COALESCE(NULLIF(TRIM(estado), ''), 'Disponible') = 'Disponible'
                    THEN 'Agotado'
                    ELSE estado
                END,
                actualizado_en = ?
            WHERE id = ?
        """, (
            stock_total,
            float(total["vendidas_total"] or 0),
            float(total["stock_minimo_ref"] or 0),
            stock_total,
            fecha,
            articulo["id"],
        ))


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"No encontré la base de datos: {DB_PATH}")
        sys.exit(1)

    backup_path = backup_db(DB_PATH)
    print(f"Respaldo creado: {backup_path}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    try:
        cur.execute("PRAGMA foreign_keys = ON")
        crear_tablas_base(cur)

        add_column_if_missing(cur, "usuarios", "establecimiento_id", "INTEGER")
        add_column_if_missing(cur, "facturas_vehiculo", "establecimiento_id", "INTEGER")
        add_column_if_missing(cur, "factura_articulos", "establecimiento_id", "INTEGER")
        add_column_if_missing(cur, "articulo_movimientos", "establecimiento_id", "INTEGER")

        sedes = concesionarias_activas(cur)
        if not sedes:
            print("Aviso: no hay concesionarias activas. Crea al menos una para separar el stock público.")
        else:
            principal = sedes[0]
            migrados = migrar_stock_global_a_concesionaria(cur, principal["id"])
            print(f"Concesionaria base para stock anterior: {principal['nombre']}")
            print(f"Artículos migrados desde stock global: {migrados}")

        recalcular_totales_articulos(cur)
        con.commit()
        print("Migración de stock por concesionarias aplicada correctamente.")

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
