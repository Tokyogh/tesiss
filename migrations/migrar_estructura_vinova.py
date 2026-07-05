#!/usr/bin/env python3
"""
Migración de estructura general VINOVA.

Este script contiene las migraciones antiguas que antes estaban dentro de app.py.
Se ejecuta manualmente para mantener el arranque de la aplicación limpio.

Uso:
    python migrations/migrar_estructura_vinova.py
    python migrations/migrar_estructura_vinova.py ruta/a/vinova.db
"""

import os
import sys
import sqlite3
import threading
from datetime import datetime
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATABASE_PATH = sys.argv[1] if len(sys.argv) > 1 else os.getenv('DATABASE_PATH', os.path.join(BASE_DIR, 'vinova.db'))
MIGRACIONES_ADMIN_EJECUTADAS = False
MIGRACIONES_ADMIN_LOCK = threading.Lock()

def ejecutar_sql_seguro(cursor, sql, descripcion="operación SQL"):
    """
    Ejecuta SQL de mantenimiento sin romper el arranque si ya existen datos
    duplicados. Esto es útil para índices UNIQUE en bases antiguas.
    """

    try:
        cursor.execute(sql)
    except sqlite3.IntegrityError as error:
        print(f"Advertencia: no se pudo aplicar {descripcion}: {error}")


def agregar_columna_si_falta(cursor, tabla, columna, definicion):
    cursor.execute(f"PRAGMA table_info({tabla})")
    columnas = {fila[1] for fila in cursor.fetchall()}

    if columna not in columnas:
        cursor.execute(
            f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
        )


def tabla_existe(cursor, nombre_tabla):
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, (
        nombre_tabla,
    ))

    return cursor.fetchone() is not None


def asegurar_migraciones_admin():
    """
    Asegura estructuras administrativas sin romper bases existentes.

    Incluye:
    - Archivado de vehículos.
    - Auditoría de canjes reversados.
    - Estado activo/fechas para usuarios.
    - Índices UNIQUE para datos críticos cuando no existen duplicados previos.

    La migración se ejecuta una sola vez por proceso para no repetir ALTER/CREATE
    en cada request. Si falla, no se marca como ejecutada y podrá reintentarse.
    """

    global MIGRACIONES_ADMIN_EJECUTADAS

    if MIGRACIONES_ADMIN_EJECUTADAS:
        return

    with MIGRACIONES_ADMIN_LOCK:
        if MIGRACIONES_ADMIN_EJECUTADAS:
            return

        conexion = sqlite3.connect(DATABASE_PATH)
        conexion.row_factory = sqlite3.Row
        conexion.execute("PRAGMA foreign_keys = ON")
        cursor = conexion.cursor()

        try:
            if tabla_existe(cursor, "vehiculos"):
                columnas_vehiculos = {
                    "archivado": "INTEGER DEFAULT 0",
                    "archivado_en": "TEXT",
                    "archivado_por": "INTEGER",
                    "motivo_archivado": "TEXT",
                    "actualizado_en": "TEXT",
                    "placa": "TEXT",
                    "preview_sistemas_json": "TEXT"
                }

                for columna, definicion in columnas_vehiculos.items():
                    agregar_columna_si_falta(cursor, "vehiculos", columna, definicion)

                ejecutar_sql_seguro(
                    cursor,
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_codigo_catalogo_unico
                    ON vehiculos(codigo_catalogo)
                    WHERE codigo_catalogo IS NOT NULL AND TRIM(codigo_catalogo) != ''
                    """,
                    "índice único de código de catálogo"
                )

            if tabla_existe(cursor, "codigos_vehiculo"):
                ejecutar_sql_seguro(
                    cursor,
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_codigo_unico
                    ON codigos_vehiculo(codigo)
                    WHERE codigo IS NOT NULL AND TRIM(codigo) != ''
                    """,
                    "índice único de código de canje"
                )

                ejecutar_sql_seguro(
                    cursor,
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_un_codigo_por_vehiculo
                    ON codigos_vehiculo(vehiculo_id)
                    WHERE vehiculo_id IS NOT NULL
                    """,
                    "índice único de un código por vehículo"
                )

            if tabla_existe(cursor, "usuarios"):
                columnas_usuarios = {
                    "activo": "INTEGER DEFAULT 1",
                    "creado_en": "TEXT",
                    "actualizado_en": "TEXT",
                    "establecimiento": "TEXT",
                    "cedula": "TEXT",
                    "reset_token_hash": "TEXT",
                    "reset_token_expira": "TEXT",
                    "notificar_correo": "INTEGER DEFAULT 1",
                    "notificar_mantenimientos": "INTEGER DEFAULT 1",
                    "notificar_alertas": "INTEGER DEFAULT 1",
                    "notificar_facturas": "INTEGER DEFAULT 1",
                    "notificar_recordatorios": "INTEGER DEFAULT 0"
                }

                for columna, definicion in columnas_usuarios.items():
                    agregar_columna_si_falta(cursor, "usuarios", columna, definicion)

                ejecutar_sql_seguro(
                    cursor,
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_correo_unico
                    ON usuarios(correo)
                    WHERE correo IS NOT NULL AND TRIM(correo) != ''
                    """,
                    "índice único de correo de usuario"
                )

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mensajes_contacto (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    correo TEXT NOT NULL,
                    telefono TEXT,
                    asunto TEXT,
                    mensaje TEXT NOT NULL,
                    ip TEXT,
                    user_agent TEXT,
                    estado TEXT DEFAULT 'Nuevo',
                    creado_en TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canjes_reversados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_vehiculo_id INTEGER,
                    usuario_id INTEGER,
                    vehiculo_id INTEGER,
                    codigo_vehiculo_id INTEGER,
                    codigo_canje TEXT,
                    usuario_nombre TEXT,
                    usuario_correo TEXT,
                    vehiculo_referencia TEXT,
                    vehiculo_descripcion TEXT,
                    kilometraje_inicial INTEGER,
                    fecha_registro_original TEXT,
                    reversado_por INTEGER,
                    reversado_en TEXT,
                    motivo TEXT
                )
            """)

            cursor.execute("""
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

            if tabla_existe(cursor, "mantenimientos"):
                columnas_mantenimientos = {
                    "registrado_por": "INTEGER",
                    "kilometraje_actual": "INTEGER",
                    "intervalo_km": "INTEGER",
                    "intervalo_meses": "INTEGER",
                    "proximo_kilometraje": "INTEGER",
                    "proxima_fecha": "TEXT",
                    "observaciones": "TEXT",
                    "establecimiento": "TEXT",
                    "estado": "TEXT DEFAULT 'Realizado'",
                    "anulado": "INTEGER DEFAULT 0",
                    "anulado_por": "INTEGER",
                    "anulado_en": "TEXT",
                    "motivo_anulacion": "TEXT"
                }

                for columna, definicion in columnas_mantenimientos.items():
                    agregar_columna_si_falta(cursor, "mantenimientos", columna, definicion)

                cursor.execute("""
                    UPDATE mantenimientos
                    SET
                        kilometraje_actual = COALESCE(kilometraje_actual, kilometraje),
                        proximo_kilometraje = COALESCE(proximo_kilometraje, proximo_servicio_km),
                        proxima_fecha = COALESCE(proxima_fecha, proximo_servicio_fecha),
                        establecimiento = COALESCE(establecimiento, taller),
                        observaciones = COALESCE(observaciones, descripcion),
                        estado = COALESCE(NULLIF(TRIM(estado), ''), 'Realizado'),
                        anulado = COALESCE(anulado, 0)
                """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manuales_vehiculo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehiculo_id INTEGER NOT NULL,
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

            if tabla_existe(cursor, "manuales_vehiculo"):
                columnas_manuales = {
                    "tipo_documento": "TEXT",
                    "archivo": "TEXT",
                    "enlace": "TEXT",
                    "descripcion": "TEXT",
                    "subido_por": "INTEGER",
                    "creado_en": "TEXT",
                    "activo": "INTEGER DEFAULT 1"
                }

                for columna, definicion in columnas_manuales.items():
                    agregar_columna_si_falta(cursor, "manuales_vehiculo", columna, definicion)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facturas_vehiculo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    vehiculo_id INTEGER NOT NULL,
                    usuario_vehiculo_id INTEGER,
                    numero_factura TEXT,
                    descripcion TEXT,
                    archivo TEXT,
                    enlace TEXT,
                    fecha_factura TEXT,
                    monto REAL DEFAULT 0,
                    establecimiento TEXT,
                    subido_por INTEGER,
                    creado_en TEXT,
                    actualizado_en TEXT,
                    activo INTEGER DEFAULT 1,
                    anulado_por INTEGER,
                    anulado_en TEXT,
                    motivo_anulacion TEXT
                )
            """)

            if tabla_existe(cursor, "facturas_vehiculo"):
                columnas_facturas = {
                    "usuario_vehiculo_id": "INTEGER",
                    "numero_factura": "TEXT",
                    "descripcion": "TEXT",
                    "archivo": "TEXT",
                    "enlace": "TEXT",
                    "fecha_factura": "TEXT",
                    "monto": "REAL DEFAULT 0",
                    "establecimiento": "TEXT",
                    "subido_por": "INTEGER",
                    "creado_en": "TEXT",
                    "actualizado_en": "TEXT",
                    "activo": "INTEGER DEFAULT 1",
                    "anulado_por": "INTEGER",
                    "anulado_en": "TEXT",
                    "motivo_anulacion": "TEXT"
                }

                for columna, definicion in columnas_facturas.items():
                    agregar_columna_si_falta(cursor, "facturas_vehiculo", columna, definicion)

                cursor.execute("""
                    UPDATE facturas_vehiculo
                    SET activo = COALESCE(activo, 1),
                        monto = COALESCE(monto, 0),
                        creado_en = COALESCE(creado_en, CURRENT_TIMESTAMP)
                """)

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_mantenimientos_usuario_fecha
                ON mantenimientos(usuario_id, fecha_servicio)
                """,
                "índice de mantenimientos por usuario y fecha"
            )

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_mantenimientos_vehiculo
                ON mantenimientos(vehiculo_id)
                """,
                "índice de mantenimientos por vehículo"
            )

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_mantenimientos_anulado
                ON mantenimientos(anulado)
                """,
                "índice de mantenimientos anulados"
            )

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_manuales_vehiculo
                ON manuales_vehiculo(vehiculo_id, activo)
                """,
                "índice de manuales por vehículo"
            )

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_facturas_usuario
                ON facturas_vehiculo(usuario_id, activo)
                """,
                "índice de facturas por usuario"
            )

            ejecutar_sql_seguro(
                cursor,
                """
                CREATE INDEX IF NOT EXISTS idx_facturas_vehiculo
                ON facturas_vehiculo(vehiculo_id, activo)
                """,
                "índice de facturas por vehículo"
            )


            # ================= MODELOS BASE / RECURSOS COMPARTIDOS =================

            cursor.execute("""
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
                    preview_sistemas_json TEXT,
                    creado_por INTEGER,
                    creado_en TEXT,
                    actualizado_en TEXT,
                    activo INTEGER DEFAULT 1
                )
            """)

            agregar_columna_si_falta(cursor, "vehiculo_modelos", "preview_sistemas_json", "TEXT")

            if tabla_existe(cursor, "vehiculos"):
                agregar_columna_si_falta(cursor, "vehiculos", "modelo_base_id", "INTEGER")
                agregar_columna_si_falta(cursor, "vehiculos", "preview_sistemas_json", "TEXT")

                cursor.execute("""
                    SELECT DISTINCT
                        TRIM(marca) AS marca,
                        TRIM(modelo) AS modelo,
                        anio,
                        COALESCE(tipo_vehiculo, '') AS tipo_vehiculo,
                        COALESCE(combustible, '') AS combustible,
                        COALESCE(transmision, '') AS transmision,
                        COALESCE(modelo_3d, '') AS modelo_3d,
                        COALESCE(modelo_3d_id, '') AS modelo_3d_id,
                        COALESCE(modelo_3d_tipo, 'glb') AS modelo_3d_tipo,
                        COALESCE(preview_sistemas_json, '') AS preview_sistemas_json,
                        COALESCE(creado_por, NULL) AS creado_por
                    FROM vehiculos
                    WHERE TRIM(COALESCE(marca, '')) != ''
                      AND TRIM(COALESCE(modelo, '')) != ''
                      AND anio IS NOT NULL
                """)

                modelos_existentes = cursor.fetchall()
                ahora_modelo = fecha_actual()

                for modelo_base in modelos_existentes:
                    cursor.execute("""
                        SELECT id, modelo_3d, modelo_3d_id, modelo_3d_tipo
                        FROM vehiculo_modelos
                        WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
                          AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
                          AND anio = ?
                        LIMIT 1
                    """, (modelo_base[0], modelo_base[1], modelo_base[2]))
                    fila_modelo = cursor.fetchone()

                    if fila_modelo:
                        modelo_id = fila_modelo[0]
                        cursor.execute("""
                            UPDATE vehiculo_modelos
                            SET
                                tipo_vehiculo = COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), ?),
                                combustible = COALESCE(NULLIF(TRIM(combustible), ''), ?),
                                transmision = COALESCE(NULLIF(TRIM(transmision), ''), ?),
                                modelo_3d = COALESCE(NULLIF(TRIM(modelo_3d), ''), ?),
                                modelo_3d_id = COALESCE(NULLIF(TRIM(modelo_3d_id), ''), ?),
                                modelo_3d_tipo = COALESCE(NULLIF(TRIM(modelo_3d_tipo), ''), ?),
                                preview_sistemas_json = COALESCE(NULLIF(TRIM(preview_sistemas_json), ''), ?),
                                actualizado_en = COALESCE(actualizado_en, ?)
                            WHERE id = ?
                        """, (modelo_base[3], modelo_base[4], modelo_base[5], modelo_base[6], modelo_base[7], modelo_base[8], modelo_base[9], ahora_modelo, modelo_id))
                    else:
                        cursor.execute("""
                            INSERT INTO vehiculo_modelos (
                                marca, modelo, anio, tipo_vehiculo, combustible, transmision,
                                modelo_3d, modelo_3d_id, modelo_3d_tipo, preview_sistemas_json, creado_por, creado_en, actualizado_en, activo
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """, (*modelo_base, ahora_modelo, ahora_modelo))
                        modelo_id = cursor.lastrowid

                    cursor.execute("""
                        UPDATE vehiculos
                        SET
                            modelo_base_id = ?,
                            modelo_3d = COALESCE(NULLIF(TRIM(modelo_3d), ''), (SELECT modelo_3d FROM vehiculo_modelos WHERE id = ?)),
                            modelo_3d_id = COALESCE(NULLIF(TRIM(modelo_3d_id), ''), (SELECT modelo_3d_id FROM vehiculo_modelos WHERE id = ?)),
                            modelo_3d_tipo = COALESCE(NULLIF(TRIM(modelo_3d_tipo), ''), (SELECT modelo_3d_tipo FROM vehiculo_modelos WHERE id = ?)),
                            preview_sistemas_json = COALESCE(NULLIF(TRIM(preview_sistemas_json), ''), (SELECT preview_sistemas_json FROM vehiculo_modelos WHERE id = ?))
                        WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
                          AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
                          AND anio = ?
                          AND (modelo_base_id IS NULL OR modelo_base_id = 0)
                    """, (modelo_id, modelo_id, modelo_id, modelo_id, modelo_id, modelo_base[0], modelo_base[1], modelo_base[2]))

                ejecutar_sql_seguro(cursor, """
                    CREATE INDEX IF NOT EXISTS idx_vehiculos_modelo_base
                    ON vehiculos(modelo_base_id)
                """, "índice de vehículos por modelo base")

            cursor.execute("""
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

            if tabla_existe(cursor, "manuales_modelo"):
                columnas_manuales_modelo = {
                    "modelo_id": "INTEGER",
                    "titulo": "TEXT",
                    "tipo_documento": "TEXT",
                    "archivo": "TEXT",
                    "enlace": "TEXT",
                    "descripcion": "TEXT",
                    "subido_por": "INTEGER",
                    "creado_en": "TEXT",
                    "activo": "INTEGER DEFAULT 1"
                }
                for columna, definicion in columnas_manuales_modelo.items():
                    agregar_columna_si_falta(cursor, "manuales_modelo", columna, definicion)

            if tabla_existe(cursor, "manuales_vehiculo") and tabla_existe(cursor, "manuales_modelo"):
                cursor.execute("""
                    SELECT
                        manuales_vehiculo.*,
                        vehiculos.modelo_base_id
                    FROM manuales_vehiculo
                    INNER JOIN vehiculos ON vehiculos.id = manuales_vehiculo.vehiculo_id
                    WHERE vehiculos.modelo_base_id IS NOT NULL
                """)
                manuales_antiguos = cursor.fetchall()

                for manual in manuales_antiguos:
                    cursor.execute("""
                        SELECT id
                        FROM manuales_modelo
                        WHERE modelo_id = ?
                          AND LOWER(TRIM(titulo)) = LOWER(TRIM(?))
                          AND COALESCE(archivo, '') = COALESCE(?, '')
                          AND COALESCE(enlace, '') = COALESCE(?, '')
                        LIMIT 1
                    """, (manual["modelo_base_id"], manual["titulo"], manual["archivo"], manual["enlace"]))

                    if cursor.fetchone():
                        continue

                    cursor.execute("""
                        INSERT INTO manuales_modelo (
                            modelo_id, titulo, tipo_documento, archivo, enlace, descripcion, subido_por, creado_en, activo
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        manual["modelo_base_id"], manual["titulo"], manual["tipo_documento"], manual["archivo"],
                        manual["enlace"], manual["descripcion"], manual["subido_por"], manual["creado_en"], manual["activo"]
                    ))

            ejecutar_sql_seguro(cursor, """
                CREATE INDEX IF NOT EXISTS idx_manuales_modelo
                ON manuales_modelo(modelo_id, activo)
            """, "índice de manuales por modelo")

            # Facturas generadas por VINOVA
            if tabla_existe(cursor, "facturas_vehiculo"):
                columnas_facturas_generadas = {
                    "mantenimiento_id": "INTEGER",
                    "tipo_factura": "TEXT DEFAULT 'Manual'",
                    "concepto": "TEXT",
                    "subtotal": "REAL DEFAULT 0",
                    "impuesto": "REAL DEFAULT 0",
                    "total": "REAL DEFAULT 0",
                    "hora_factura": "TEXT",
                    "generado_por": "INTEGER",
                    "archivo_pdf": "TEXT",
                    "estado": "TEXT DEFAULT 'Generada'",
                    "anulado": "INTEGER DEFAULT 0"
                }

                for columna, definicion in columnas_facturas_generadas.items():
                    agregar_columna_si_falta(cursor, "facturas_vehiculo", columna, definicion)

                cursor.execute("""
                    UPDATE facturas_vehiculo
                    SET
                        tipo_factura = COALESCE(NULLIF(TRIM(tipo_factura), ''), 'Manual'),
                        concepto = COALESCE(NULLIF(TRIM(concepto), ''), descripcion, 'Factura VINOVA'),
                        subtotal = COALESCE(NULLIF(subtotal, 0), monto, 0),
                        total = COALESCE(NULLIF(total, 0), monto, subtotal, 0),
                        generado_por = COALESCE(generado_por, subido_por),
                        archivo_pdf = COALESCE(NULLIF(TRIM(archivo_pdf), ''), archivo),
                        estado = COALESCE(NULLIF(TRIM(estado), ''), 'Generada'),
                        anulado = COALESCE(anulado, CASE WHEN COALESCE(activo, 1) = 1 THEN 0 ELSE 1 END)
                """)

            conexion.commit()
            MIGRACIONES_ADMIN_EJECUTADAS = True
        finally:
            conexion.close()


def fecha_actual():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == '__main__':
    if not os.path.exists(DATABASE_PATH):
        print(f'No se encontró la base de datos: {DATABASE_PATH}')
        raise SystemExit(1)

    asegurar_migraciones_admin()
    print(f'Migraciones de estructura VINOVA aplicadas correctamente en: {DATABASE_PATH}')
