
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


MIGRATION_NAME = "20260705_articulos_inventario.sql"

SQL = r"""
-- VINOVA - Módulo de artículos e inventario
-- Ejecutar una sola vez sobre vinova.db.

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
);

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
);

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
);

CREATE INDEX IF NOT EXISTS idx_articulos_estado ON articulos(activo, archivado, categoria);
CREATE INDEX IF NOT EXISTS idx_articulos_nombre ON articulos(nombre, codigo_articulo, marca);
CREATE INDEX IF NOT EXISTS idx_articulo_movimientos_articulo ON articulo_movimientos(articulo_id, creado_en);
CREATE INDEX IF NOT EXISTS idx_factura_articulos_factura ON factura_articulos(factura_id);
""".strip() + "\n"


def find_project_root() -> Path:
    """Busca vinova.db desde la carpeta actual hacia arriba."""
    current = Path.cwd().resolve()

    for candidate in [current, *current.parents]:
        if (candidate / "vinova.db").exists():
            return candidate

    raise SystemExit(
        "No encontré vinova.db.\n"
        "Ejecuta este archivo desde la raíz del proyecto, por ejemplo:\n"
        "C:\\Users\\elias\\Downloads\\web_carros"
    )


def backup_file(path: Path, label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_{label}_{timestamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_migration_file(root: Path) -> Path:
    migrations_dir = root / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)

    migration_path = migrations_dir / MIGRATION_NAME
    if not migration_path.exists():
        migration_path.write_text(SQL, encoding="utf-8")
        print(f"Archivo SQL creado: {migration_path.relative_to(root)}")
    else:
        print(f"Archivo SQL ya existe: {migration_path.relative_to(root)}")

    return migration_path


def apply_migration(db_path: Path) -> None:
    backup_path = backup_file(db_path, "antes_articulos")
    print(f"Respaldo creado: {backup_path.name}")

    con = sqlite3.connect(db_path)
    try:
        con.executescript(SQL)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def ensure_static_folder(root: Path) -> None:
    folder = root / "static" / "img" / "articulos"
    folder.mkdir(parents=True, exist_ok=True)

    gitkeep = folder / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")

    print(f"Carpeta lista: {folder.relative_to(root)}")


def patch_app_import(root: Path) -> None:
    app_path = root / "app.py"
    route_path = root / "vinova" / "routes" / "articulos.py"

    if not app_path.exists():
        print("Aviso: no encontré app.py. Revisa manualmente el import de articulos.")
        return

    if not route_path.exists():
        print(
            "Aviso: no encontré vinova/routes/articulos.py.\n"
            "       Copia primero los archivos del ZIP del módulo de artículos."
        )
        return

    text = app_path.read_text(encoding="utf-8")

    if "from vinova.routes import articulos" in text:
        print("app.py ya tiene importado articulos.")
        return

    backup_path = backup_file(app_path, "antes_import_articulos")
    import_line = "from vinova.routes import articulos  # noqa: F401\n"

    marker = "from vinova.routes import catalogo  # noqa: F401\n"
    if marker in text:
        text = text.replace(marker, marker + import_line)
    else:
        if_main = "\nif __name__ == \"__main__\":"
        if if_main in text:
            text = text.replace(if_main, "\n" + import_line + if_main)
        else:
            text = text.rstrip() + "\n" + import_line

    app_path.write_text(text, encoding="utf-8")
    print(f"app.py actualizado. Respaldo: {backup_path.name}")


def verify_tables(db_path: Path) -> None:
    expected = {"articulos", "articulo_movimientos", "factura_articulos"}

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?)",
            tuple(sorted(expected)),
        ).fetchall()
    finally:
        con.close()

    found = {row[0] for row in rows}
    missing = expected - found

    if missing:
        raise SystemExit(f"Faltan tablas por crear: {', '.join(sorted(missing))}")

    print("Tablas verificadas: articulos, articulo_movimientos, factura_articulos")


def main() -> None:
    root = find_project_root()
    db_path = root / "vinova.db"

    print("Raíz del proyecto:", root)
    print("Base de datos:", db_path.name)
    print("-" * 60)

    write_migration_file(root)
    apply_migration(db_path)
    ensure_static_folder(root)
    patch_app_import(root)
    verify_tables(db_path)

    print("-" * 60)
    print("Migración de artículos aplicada correctamente.")
    print("Ahora reinicia Flask con: python app.py")


if __name__ == "__main__":
    main()
