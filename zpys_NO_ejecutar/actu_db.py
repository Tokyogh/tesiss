"""
unificacion
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_NAME = "vinova.db"
BACKUP_DIR_NAME = "backups"


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db_path() -> Path:
    base = Path(__file__).resolve().parent
    if len(sys.argv) >= 2:
        p = Path(sys.argv[1]).expanduser()
        return p if p.is_absolute() else base / p
    return base / DEFAULT_DB_NAME


def backup(path: Path) -> Path:
    carpeta = path.parent / BACKUP_DIR_NAME
    carpeta.mkdir(exist_ok=True)
    destino = carpeta / f"{path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    shutil.copy2(path, destino)
    return destino


def tabla_existe(cur: sqlite3.Cursor, tabla: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cur.fetchone() is not None


def columnas(cur: sqlite3.Cursor, tabla: str) -> set[str]:
    if not tabla_existe(cur, tabla):
        return set()
    cur.execute(f"PRAGMA table_info({tabla})")
    return {r[1] for r in cur.fetchall()}


def add_col(cur: sqlite3.Cursor, tabla: str, columna: str, definicion: str) -> None:
    if columna not in columnas(cur, tabla):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"  + {tabla}.{columna}")


def safe(cur: sqlite3.Cursor, sql: str, nombre: str) -> None:
    try:
        cur.execute(sql)
    except sqlite3.Error as e:
        print(f"  ! No se pudo aplicar {nombre}: {e}")


def crear_tablas_base(cur: sqlite3.Cursor) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculo_modelos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            anio INTEGER NOT NULL,
            tipo_vehiculo TEXT,
            combustible TEXT,
            transmision TEXT,
            modelo_3d TEXT,
            modelo_3d_id TEXT,
            modelo_3d_tipo TEXT DEFAULT 'glb',
            creado_por INTEGER,
            creado_en TEXT,
            actualizado_en TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuales_modelo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modelo_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo_documento TEXT,
            archivo TEXT,
            enlace TEXT,
            descripcion TEXT,
            subido_por INTEGER,
            creado_en TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturas_vehiculo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            vehiculo_id INTEGER NOT NULL,
            usuario_vehiculo_id INTEGER,
            mantenimiento_id INTEGER,
            numero_factura TEXT,
            tipo_factura TEXT DEFAULT 'Manual',
            concepto TEXT,
            descripcion TEXT,
            archivo TEXT,
            archivo_pdf TEXT,
            enlace TEXT,
            fecha_factura TEXT,
            hora_factura TEXT,
            monto REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            impuesto REAL DEFAULT 0,
            total REAL DEFAULT 0,
            establecimiento TEXT,
            subido_por INTEGER,
            generado_por INTEGER,
            creado_en TEXT,
            actualizado_en TEXT,
            activo INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'Generada',
            anulado INTEGER DEFAULT 0,
            anulado_por INTEGER,
            anulado_en TEXT,
            motivo_anulacion TEXT
        )
    """)


def migrar_columnas(cur: sqlite3.Cursor) -> None:
    if tabla_existe(cur, "usuarios"):
        for col, dfn in {
            "activo": "INTEGER DEFAULT 1",
            "creado_en": "TEXT",
            "actualizado_en": "TEXT",
            "establecimiento": "TEXT",
        }.items():
            add_col(cur, "usuarios", col, dfn)

    if tabla_existe(cur, "vehiculos"):
        for col, dfn in {
            "modelo_base_id": "INTEGER",
            "archivado": "INTEGER DEFAULT 0",
            "archivado_en": "TEXT",
            "archivado_por": "INTEGER",
            "motivo_archivado": "TEXT",
            "actualizado_en": "TEXT",
            "modelo_3d_id": "TEXT",
            "modelo_3d_tipo": "TEXT DEFAULT 'glb'",
            "creado_por": "INTEGER",
            "creado_en": "TEXT",
        }.items():
            add_col(cur, "vehiculos", col, dfn)

    if tabla_existe(cur, "mantenimientos"):
        for col, dfn in {
            "registrado_por": "INTEGER",
            "kilometraje_actual": "INTEGER",
            "intervalo_km": "INTEGER",
            "intervalo_meses": "INTEGER",
            "proximo_kilometraje": "INTEGER",
            "proxima_fecha": "TEXT",
            "observaciones": "TEXT",
            "establecimiento": "TEXT",
            "estado": "TEXT DEFAULT 'Realizado'",
            "costo": "REAL DEFAULT 0",
            "anulado": "INTEGER DEFAULT 0",
            "anulado_por": "INTEGER",
            "anulado_en": "TEXT",
            "motivo_anulacion": "TEXT",
        }.items():
            add_col(cur, "mantenimientos", col, dfn)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mantenimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                vehiculo_id INTEGER NOT NULL,
                usuario_vehiculo_id INTEGER,
                registrado_por INTEGER,
                tipo_servicio TEXT NOT NULL,
                descripcion TEXT,
                kilometraje_actual INTEGER,
                fecha_servicio TEXT NOT NULL,
                intervalo_km INTEGER,
                intervalo_meses INTEGER,
                proximo_kilometraje INTEGER,
                proxima_fecha TEXT,
                observaciones TEXT,
                establecimiento TEXT,
                estado TEXT DEFAULT 'Realizado',
                costo REAL DEFAULT 0,
                taller TEXT,
                kilometraje INTEGER,
                proximo_servicio_fecha TEXT,
                proximo_servicio_km INTEGER,
                creado_en TEXT,
                actualizado_en TEXT,
                anulado INTEGER DEFAULT 0,
                anulado_por INTEGER,
                anulado_en TEXT,
                motivo_anulacion TEXT
            )
        """)

    for col, dfn in {
        "usuario_vehiculo_id": "INTEGER",
        "mantenimiento_id": "INTEGER",
        "numero_factura": "TEXT",
        "tipo_factura": "TEXT DEFAULT 'Manual'",
        "concepto": "TEXT",
        "descripcion": "TEXT",
        "archivo": "TEXT",
        "archivo_pdf": "TEXT",
        "enlace": "TEXT",
        "fecha_factura": "TEXT",
        "hora_factura": "TEXT",
        "monto": "REAL DEFAULT 0",
        "subtotal": "REAL DEFAULT 0",
        "impuesto": "REAL DEFAULT 0",
        "total": "REAL DEFAULT 0",
        "establecimiento": "TEXT",
        "subido_por": "INTEGER",
        "generado_por": "INTEGER",
        "creado_en": "TEXT",
        "actualizado_en": "TEXT",
        "activo": "INTEGER DEFAULT 1",
        "estado": "TEXT DEFAULT 'Generada'",
        "anulado": "INTEGER DEFAULT 0",
        "anulado_por": "INTEGER",
        "anulado_en": "TEXT",
        "motivo_anulacion": "TEXT",
    }.items():
        add_col(cur, "facturas_vehiculo", col, dfn)


def get_modelo(cur: sqlite3.Cursor, marca: str, modelo: str, anio: int, datos: dict[str, Any]) -> int:
    cur.execute("""
        SELECT id
        FROM vehiculo_modelos
        WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
          AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
          AND anio = ?
        LIMIT 1
    """, (marca, modelo, anio))
    row = cur.fetchone()
    if row:
        modelo_id = row[0]
        cur.execute("""
            UPDATE vehiculo_modelos
            SET
                tipo_vehiculo = COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), ?),
                combustible = COALESCE(NULLIF(TRIM(combustible), ''), ?),
                transmision = COALESCE(NULLIF(TRIM(transmision), ''), ?),
                modelo_3d = COALESCE(NULLIF(TRIM(modelo_3d), ''), ?),
                modelo_3d_id = COALESCE(NULLIF(TRIM(modelo_3d_id), ''), ?),
                modelo_3d_tipo = COALESCE(NULLIF(TRIM(modelo_3d_tipo), ''), ?),
                actualizado_en = COALESCE(actualizado_en, ?)
            WHERE id = ?
        """, (
            datos.get("tipo_vehiculo", ""), datos.get("combustible", ""), datos.get("transmision", ""),
            datos.get("modelo_3d", ""), datos.get("modelo_3d_id", ""), datos.get("modelo_3d_tipo", "glb"), ahora(), modelo_id
        ))
        return modelo_id

    cur.execute("""
        INSERT INTO vehiculo_modelos (
            marca, modelo, anio, tipo_vehiculo, combustible, transmision,
            modelo_3d, modelo_3d_id, modelo_3d_tipo, creado_por, creado_en, actualizado_en, activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        marca, modelo, anio,
        datos.get("tipo_vehiculo", ""), datos.get("combustible", ""), datos.get("transmision", ""),
        datos.get("modelo_3d", ""), datos.get("modelo_3d_id", ""), datos.get("modelo_3d_tipo", "glb"),
        datos.get("creado_por"), ahora(), ahora()
    ))
    return cur.lastrowid


def migrar_modelos_y_manuales(cur: sqlite3.Cursor) -> None:
    if not tabla_existe(cur, "vehiculos"):
        return

    cur.execute("""
        SELECT *
        FROM vehiculos
        WHERE TRIM(COALESCE(marca, '')) != ''
          AND TRIM(COALESCE(modelo, '')) != ''
          AND anio IS NOT NULL
    """)
    vehiculos = cur.fetchall()

    for v in vehiculos:
        datos = dict(v)
        modelo_id = get_modelo(cur, datos["marca"], datos["modelo"], int(datos["anio"]), datos)
        cur.execute("UPDATE vehiculos SET modelo_base_id = ? WHERE id = ?", (modelo_id, datos["id"]))

    if tabla_existe(cur, "manuales_vehiculo"):
        cur.execute("""
            SELECT manuales_vehiculo.*, vehiculos.modelo_base_id
            FROM manuales_vehiculo
            INNER JOIN vehiculos ON vehiculos.id = manuales_vehiculo.vehiculo_id
            WHERE vehiculos.modelo_base_id IS NOT NULL
        """)
        manuales = cur.fetchall()
        for m in manuales:
            d = dict(m)
            cur.execute("""
                SELECT id FROM manuales_modelo
                WHERE modelo_id = ?
                  AND LOWER(TRIM(titulo)) = LOWER(TRIM(?))
                  AND COALESCE(archivo, '') = COALESCE(?, '')
                  AND COALESCE(enlace, '') = COALESCE(?, '')
                LIMIT 1
            """, (d["modelo_base_id"], d["titulo"], d.get("archivo"), d.get("enlace")))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO manuales_modelo (modelo_id, titulo, tipo_documento, archivo, enlace, descripcion, subido_por, creado_en, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["modelo_base_id"], d["titulo"], d.get("tipo_documento"), d.get("archivo"), d.get("enlace"),
                d.get("descripcion"), d.get("subido_por"), d.get("creado_en") or ahora(), d.get("activo", 1)
            ))


def normalizar_datos(cur: sqlite3.Cursor) -> None:
    if tabla_existe(cur, "vehiculos"):
        cur.execute("UPDATE vehiculos SET archivado = COALESCE(archivado, 0)")
    if tabla_existe(cur, "usuarios"):
        cur.execute("UPDATE usuarios SET activo = COALESCE(activo, 1)")
    if tabla_existe(cur, "mantenimientos"):
        cur.execute("""
            UPDATE mantenimientos
            SET
                kilometraje_actual = COALESCE(kilometraje_actual, kilometraje),
                proximo_kilometraje = COALESCE(proximo_kilometraje, proximo_servicio_km),
                proxima_fecha = COALESCE(proxima_fecha, proximo_servicio_fecha),
                establecimiento = COALESCE(NULLIF(TRIM(establecimiento), ''), taller, 'VINOVA'),
                observaciones = COALESCE(NULLIF(TRIM(observaciones), ''), descripcion),
                estado = COALESCE(NULLIF(TRIM(estado), ''), 'Realizado'),
                costo = COALESCE(costo, 0),
                anulado = COALESCE(anulado, 0)
        """)
    cur.execute("""
        UPDATE facturas_vehiculo
        SET
            activo = COALESCE(activo, 1),
            anulado = COALESCE(anulado, CASE WHEN COALESCE(activo, 1) = 1 THEN 0 ELSE 1 END),
            tipo_factura = COALESCE(NULLIF(TRIM(tipo_factura), ''), 'Manual'),
            concepto = COALESCE(NULLIF(TRIM(concepto), ''), descripcion, 'Factura VINOVA'),
            subtotal = COALESCE(NULLIF(subtotal, 0), monto, 0),
            total = COALESCE(NULLIF(total, 0), monto, subtotal, 0),
            generado_por = COALESCE(generado_por, subido_por),
            archivo_pdf = COALESCE(NULLIF(TRIM(archivo_pdf), ''), archivo),
            estado = COALESCE(NULLIF(TRIM(estado), ''), 'Generada'),
            creado_en = COALESCE(creado_en, ?)
    """, (ahora(),))


def indices(cur: sqlite3.Cursor) -> None:
    safe(cur, "CREATE INDEX IF NOT EXISTS idx_vehiculos_modelo_base ON vehiculos(modelo_base_id)", "idx_vehiculos_modelo_base")
    safe(cur, "CREATE INDEX IF NOT EXISTS idx_manuales_modelo ON manuales_modelo(modelo_id, activo)", "idx_manuales_modelo")
    safe(cur, "CREATE INDEX IF NOT EXISTS idx_facturas_usuario ON facturas_vehiculo(usuario_id, activo)", "idx_facturas_usuario")
    safe(cur, "CREATE INDEX IF NOT EXISTS idx_facturas_vehiculo ON facturas_vehiculo(vehiculo_id, activo)", "idx_facturas_vehiculo")
    safe(cur, "CREATE INDEX IF NOT EXISTS idx_facturas_mantenimiento ON facturas_vehiculo(mantenimiento_id)", "idx_facturas_mantenimiento")
    safe(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_codigo_catalogo_unico ON vehiculos(codigo_catalogo) WHERE codigo_catalogo IS NOT NULL AND TRIM(codigo_catalogo) != ''", "idx_vehiculos_codigo_catalogo_unico")


def main() -> None:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"No encontré la base: {path}")

    print("========================================")
    print(" Migración VINOVA profesional")
    print("========================================")
    print(f"Base: {path}")
    b = backup(path)
    print(f"Backup: {b}")

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("PRAGMA foreign_keys = OFF")
        crear_tablas_base(cur)
        migrar_columnas(cur)
        migrar_modelos_y_manuales(cur)
        normalizar_datos(cur)
        indices(cur)
        con.commit()
        print("Base actualizada correctamente.")
    except Exception:
        con.rollback()
        print("ERROR: no se guardaron cambios incompletos. Usa el backup si lo necesitas.")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
