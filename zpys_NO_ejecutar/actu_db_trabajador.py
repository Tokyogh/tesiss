"""
Migración de base de datos VINOVA
=================================

Uso recomendado:
1. Copia este archivo en la carpeta raíz del proyecto VINOVA, junto a app.py y vinova.db.
2. Detén el servidor Flask si está encendido.
3. Ejecuta:

   python actualizar_vinova_db.py

Opcional, si tu base tiene otro nombre temporal:

   python actualizar_vinova_db.py "vinova(2).db"

Este script NO borra tu base. Antes de tocarla crea una copia en la carpeta backups/.
Actualiza la base existente para el módulo de mantenimiento empresarial:
- agrega establecimiento a usuarios/trabajadores;
- amplía mantenimientos para registrar quién hizo el servicio;
- calcula próxima fecha y próximo kilometraje cuando falten;
- crea manuales_vehiculo para manuales por vehículo.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


DEFAULT_DB_NAME = "vinova.db"
BACKUP_DIR_NAME = "backups"


def ahora_texto() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalizar_texto(texto: object) -> str:
    valor = str(texto or "").strip().lower()
    valor = unicodedata.normalize("NFD", valor)
    valor = "".join(caracter for caracter in valor if unicodedata.category(caracter) != "Mn")
    return valor


def normalizar_entero(valor: object) -> Optional[int]:
    if valor is None:
        return None

    if isinstance(valor, int):
        return valor if valor >= 0 else None

    if isinstance(valor, float):
        return int(valor) if valor >= 0 else None

    texto = str(valor).strip().lower()

    if not texto:
        return None

    texto = texto.replace("kilómetros", "")
    texto = texto.replace("kilometros", "")
    texto = texto.replace("kms", "")
    texto = texto.replace("km", "")
    texto = texto.replace(".", "")
    texto = texto.replace(",", "")
    texto = "".join(texto.split())

    if not texto.isdigit():
        return None

    numero = int(texto)
    return numero if numero >= 0 else None


def sumar_meses(fecha: object, meses: int) -> Optional[str]:
    texto = str(fecha or "").strip()[:10]

    if not texto:
        return None

    try:
        fecha_obj = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return None

    mes_total = fecha_obj.month - 1 + int(meses or 0)
    anio = fecha_obj.year + mes_total // 12
    mes = mes_total % 12 + 1

    dias_mes = [
        31,
        29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    dia = min(fecha_obj.day, dias_mes[mes - 1])

    return datetime(anio, mes, dia).strftime("%Y-%m-%d")


def reglas_mantenimiento(tipo_servicio: object) -> Tuple[int, int]:
    tipo = normalizar_texto(tipo_servicio)

    if "aceite" in tipo:
        return 5000, 6

    if "revision general" in tipo or "general" in tipo:
        return 10000, 12

    if "freno" in tipo:
        return 15000, 12

    if "llanta" in tipo or "neumatic" in tipo:
        return 10000, 12

    if "bateria" in tipo:
        return 20000, 18

    return 10000, 12


def calcular_proximo_mantenimiento(
    tipo_servicio: object,
    kilometraje_actual: object,
    fecha_servicio: object,
) -> Tuple[int, int, Optional[int], Optional[str]]:
    intervalo_km, intervalo_meses = reglas_mantenimiento(tipo_servicio)
    kilometraje = normalizar_entero(kilometraje_actual)

    proximo_kilometraje = None
    if kilometraje is not None:
        proximo_kilometraje = kilometraje + intervalo_km

    proxima_fecha = sumar_meses(fecha_servicio, intervalo_meses)

    return intervalo_km, intervalo_meses, proximo_kilometraje, proxima_fecha


def tabla_existe(cursor: sqlite3.Cursor, tabla: str) -> bool:
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (tabla,),
    )
    return cursor.fetchone() is not None


def columnas_tabla(cursor: sqlite3.Cursor, tabla: str) -> set[str]:
    if not tabla_existe(cursor, tabla):
        return set()

    cursor.execute(f"PRAGMA table_info({tabla})")
    return {fila[1] for fila in cursor.fetchall()}


def agregar_columna_si_falta(
    cursor: sqlite3.Cursor,
    tabla: str,
    columna: str,
    definicion: str,
) -> bool:
    columnas = columnas_tabla(cursor, tabla)

    if columna in columnas:
        return False

    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    print(f"  + Columna agregada: {tabla}.{columna}")
    return True


def ejecutar_sql_seguro(cursor: sqlite3.Cursor, sql: str, descripcion: str) -> None:
    try:
        cursor.execute(sql)
    except sqlite3.IntegrityError as error:
        print(f"  ! No se pudo aplicar {descripcion}: {error}")
    except sqlite3.OperationalError as error:
        print(f"  ! No se pudo aplicar {descripcion}: {error}")


def migrar_usuarios(cursor: sqlite3.Cursor) -> None:
    if not tabla_existe(cursor, "usuarios"):
        raise RuntimeError("No existe la tabla usuarios. Verifica que esta sea la base vinova.db correcta.")

    print("- Revisando tabla usuarios...")

    columnas_usuarios = {
        "activo": "INTEGER DEFAULT 1",
        "creado_en": "TEXT",
        "actualizado_en": "TEXT",
        "establecimiento": "TEXT",
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
        "índice único de correo de usuario",
    )

    cursor.execute(
        """
        UPDATE usuarios
        SET activo = COALESCE(activo, 1)
        WHERE activo IS NULL
        """
    )


def migrar_vehiculos(cursor: sqlite3.Cursor) -> None:
    if not tabla_existe(cursor, "vehiculos"):
        raise RuntimeError("No existe la tabla vehiculos. Verifica que esta sea la base vinova.db correcta.")

    print("- Revisando tabla vehiculos...")

    columnas_vehiculos = {
        "archivado": "INTEGER DEFAULT 0",
        "archivado_en": "TEXT",
        "archivado_por": "INTEGER",
        "motivo_archivado": "TEXT",
        "actualizado_en": "TEXT",
    }

    for columna, definicion in columnas_vehiculos.items():
        agregar_columna_si_falta(cursor, "vehiculos", columna, definicion)

    cursor.execute(
        """
        UPDATE vehiculos
        SET archivado = COALESCE(archivado, 0)
        WHERE archivado IS NULL
        """
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_codigo_catalogo_unico
        ON vehiculos(codigo_catalogo)
        WHERE codigo_catalogo IS NOT NULL AND TRIM(codigo_catalogo) != ''
        """,
        "índice único de código de catálogo",
    )


def migrar_codigos(cursor: sqlite3.Cursor) -> None:
    if not tabla_existe(cursor, "codigos_vehiculo"):
        print("- Tabla codigos_vehiculo no existe; se omite.")
        return

    print("- Revisando tabla codigos_vehiculo...")

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_codigo_unico
        ON codigos_vehiculo(codigo)
        WHERE codigo IS NOT NULL AND TRIM(codigo) != ''
        """,
        "índice único de código de canje",
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_un_codigo_por_vehiculo
        ON codigos_vehiculo(vehiculo_id)
        WHERE vehiculo_id IS NOT NULL
        """,
        "índice único de un código por vehículo",
    )


def migrar_canjes_reversados(cursor: sqlite3.Cursor) -> None:
    print("- Revisando tabla canjes_reversados...")

    cursor.execute(
        """
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
        """
    )


def migrar_mantenimientos(cursor: sqlite3.Cursor) -> None:
    print("- Revisando tabla mantenimientos...")

    cursor.execute(
        """
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
        """
    )

    columnas_mantenimientos = {
        "registrado_por": "INTEGER",
        "descripcion": "TEXT",
        "kilometraje_actual": "INTEGER",
        "intervalo_km": "INTEGER",
        "intervalo_meses": "INTEGER",
        "proximo_kilometraje": "INTEGER",
        "proxima_fecha": "TEXT",
        "observaciones": "TEXT",
        "establecimiento": "TEXT",
        "estado": "TEXT DEFAULT 'Realizado'",
        "costo": "REAL DEFAULT 0",
        "taller": "TEXT",
        "kilometraje": "INTEGER",
        "proximo_servicio_fecha": "TEXT",
        "proximo_servicio_km": "INTEGER",
        "creado_en": "TEXT",
        "actualizado_en": "TEXT",
        "anulado": "INTEGER DEFAULT 0",
        "anulado_por": "INTEGER",
        "anulado_en": "TEXT",
        "motivo_anulacion": "TEXT",
    }

    for columna, definicion in columnas_mantenimientos.items():
        agregar_columna_si_falta(cursor, "mantenimientos", columna, definicion)

    cursor.execute(
        """
        UPDATE mantenimientos
        SET
            kilometraje_actual = COALESCE(kilometraje_actual, kilometraje),
            proximo_kilometraje = COALESCE(proximo_kilometraje, proximo_servicio_km),
            proxima_fecha = COALESCE(proxima_fecha, proximo_servicio_fecha),
            establecimiento = COALESCE(NULLIF(TRIM(establecimiento), ''), NULLIF(TRIM(taller), ''), 'VINOVA'),
            observaciones = COALESCE(NULLIF(TRIM(observaciones), ''), descripcion),
            estado = COALESCE(NULLIF(TRIM(estado), ''), 'Realizado'),
            costo = COALESCE(costo, 0),
            anulado = COALESCE(anulado, 0),
            creado_en = COALESCE(creado_en, ?),
            actualizado_en = COALESCE(actualizado_en, ?)
        """,
        (ahora_texto(), ahora_texto()),
    )

    cursor.execute(
        """
        SELECT
            id,
            tipo_servicio,
            fecha_servicio,
            kilometraje_actual,
            kilometraje
        FROM mantenimientos
        """
    )

    filas = cursor.fetchall()
    actualizados = 0

    for fila in filas:
        mantenimiento_id = fila[0]
        tipo_servicio = fila[1]
        fecha_servicio = fila[2]
        km_referencia = fila[3] if fila[3] is not None else fila[4]

        intervalo_km, intervalo_meses, proximo_km, proxima_fecha = calcular_proximo_mantenimiento(
            tipo_servicio,
            km_referencia,
            fecha_servicio,
        )

        cursor.execute(
            """
            UPDATE mantenimientos
            SET
                intervalo_km = ?,
                intervalo_meses = ?,
                proximo_kilometraje = ?,
                proxima_fecha = ?,
                proximo_servicio_km = ?,
                proximo_servicio_fecha = ?
            WHERE id = ?
            """,
            (
                intervalo_km,
                intervalo_meses,
                proximo_km,
                proxima_fecha,
                proximo_km,
                proxima_fecha,
                mantenimiento_id,
            ),
        )
        actualizados += 1

    print(f"  + Mantenimientos revisados/calculados: {actualizados}")

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_usuario_fecha
        ON mantenimientos(usuario_id, fecha_servicio)
        """,
        "índice de mantenimientos por usuario y fecha",
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_vehiculo
        ON mantenimientos(vehiculo_id)
        """,
        "índice de mantenimientos por vehículo",
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_anulado
        ON mantenimientos(anulado)
        """,
        "índice de mantenimientos anulados",
    )


def migrar_manuales(cursor: sqlite3.Cursor) -> None:
    print("- Revisando tabla manuales_vehiculo...")

    cursor.execute(
        """
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
        """
    )

    columnas_manuales = {
        "vehiculo_id": "INTEGER",
        "titulo": "TEXT",
        "tipo_documento": "TEXT",
        "archivo": "TEXT",
        "enlace": "TEXT",
        "descripcion": "TEXT",
        "subido_por": "INTEGER",
        "creado_en": "TEXT",
        "activo": "INTEGER DEFAULT 1",
    }

    for columna, definicion in columnas_manuales.items():
        try:
            agregar_columna_si_falta(cursor, "manuales_vehiculo", columna, definicion)
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        """
        UPDATE manuales_vehiculo
        SET activo = COALESCE(activo, 1)
        WHERE activo IS NULL
        """
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_manuales_vehiculo
        ON manuales_vehiculo(vehiculo_id, activo)
        """,
        "índice de manuales por vehículo",
    )


def resolver_db_path() -> Path:
    script_dir = Path(__file__).resolve().parent

    if len(sys.argv) >= 2:
        db_path = Path(sys.argv[1]).expanduser()

        if not db_path.is_absolute():
            db_path = script_dir / db_path

        return db_path

    return script_dir / DEFAULT_DB_NAME


def crear_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)

    return backup_path


def ejecutar_migracion(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(
            f"No encontré la base de datos en: {db_path}\n"
            f"Coloca este archivo junto a vinova.db o ejecuta: "
            f"python actualizar_vinova_db.py ruta/a/tu_base.db"
        )

    print("========================================")
    print(" Migración VINOVA DB")
    print("========================================")
    print(f"Base detectada: {db_path}")

    backup_path = crear_backup(db_path)
    print(f"Backup creado: {backup_path}")

    conexion = sqlite3.connect(db_path)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = OFF")

        migrar_usuarios(cursor)
        migrar_vehiculos(cursor)
        migrar_codigos(cursor)
        migrar_canjes_reversados(cursor)
        migrar_mantenimientos(cursor)
        migrar_manuales(cursor)

        conexion.commit()

        print("========================================")
        print(" Base actualizada correctamente.")
        print("========================================")
        print("Ya puedes ejecutar Flask usando tu vinova.db original.")

    except Exception:
        conexion.rollback()

        print("========================================")
        print(" ERROR: se canceló la migración.")
        print(" No se guardaron cambios incompletos.")
        print(f" Tu backup está en: {backup_path}")
        print("========================================")

        raise

    finally:
        conexion.close()


if __name__ == "__main__":
    ejecutar_migracion(resolver_db_path())