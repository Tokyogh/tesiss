import sqlite3
import shutil
from pathlib import Path

DB_NAME = "vinova.db"

# Backup de seguridad antes de modificar la base
db_path = Path(DB_NAME)

if not db_path.exists():
    raise FileNotFoundError("No se encontró vinova.db en la raíz del proyecto.")

backup_path = Path("vinova_backup_catalogo.db")

if not backup_path.exists():
    shutil.copy2(DB_NAME, backup_path)
    print("Backup creado:", backup_path)
else:
    print("Backup ya existe:", backup_path)


def obtener_columnas(cursor, tabla):
    cursor.execute(f"PRAGMA table_info({tabla})")
    return [columna[1] for columna in cursor.fetchall()]


def agregar_columna(cursor, tabla, columna, definicion):
    columnas = obtener_columnas(cursor, tabla)

    if columna not in columnas:
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"Columna agregada: {tabla}.{columna}")
    else:
        print(f"Columna ya existe: {tabla}.{columna}")


conexion = sqlite3.connect(DB_NAME)
cursor = conexion.cursor()

# ===============================
# AMPLIAR TABLA VEHICULOS
# ===============================

agregar_columna(cursor, "vehiculos", "codigo_catalogo", "TEXT")
agregar_columna(cursor, "vehiculos", "tipo_vehiculo", "TEXT DEFAULT 'SUV'")
agregar_columna(cursor, "vehiculos", "combustible", "TEXT DEFAULT 'Gasolina'")
agregar_columna(cursor, "vehiculos", "transmision", "TEXT DEFAULT 'Automática'")
agregar_columna(cursor, "vehiculos", "kilometraje", "INTEGER DEFAULT 0")
agregar_columna(cursor, "vehiculos", "precio", "REAL DEFAULT 0")
agregar_columna(cursor, "vehiculos", "descripcion", "TEXT")
agregar_columna(cursor, "vehiculos", "estado", "TEXT DEFAULT 'Disponible'")
agregar_columna(cursor, "vehiculos", "activo", "INTEGER DEFAULT 1")
agregar_columna(cursor, "vehiculos", "modelo_3d_id", "TEXT")
agregar_columna(cursor, "vehiculos", "modelo_3d_tipo", "TEXT DEFAULT 'glb'")
agregar_columna(cursor, "vehiculos", "creado_por", "INTEGER")
agregar_columna(cursor, "vehiculos", "creado_en", "TEXT")
agregar_columna(cursor, "vehiculos", "actualizado_en", "TEXT")

# Código único para identificar cada modelo del catálogo
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_codigo_catalogo
    ON vehiculos(codigo_catalogo)
""")

print("Índice único creado/verificado: idx_vehiculos_codigo_catalogo")

# Evitar que un usuario registre dos veces el mismo vehículo
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_usuario_vehiculo_unico
    ON usuarios_vehiculos(usuario_id, vehiculo_id)
""")

print("Índice único creado/verificado: idx_usuario_vehiculo_unico")

conexion.commit()
conexion.close()

print("Migración del catálogo completada correctamente.")