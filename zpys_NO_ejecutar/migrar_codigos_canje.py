import sqlite3
import shutil
from pathlib import Path

DB_NAME = "vinova.db"

db_path = Path(DB_NAME)

if not db_path.exists():
    raise FileNotFoundError("No se encontró vinova.db en la raíz del proyecto.")

backup_path = Path("vinova_backup_codigos_canje.db")

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
# TABLA CÓDIGOS DE VEHÍCULO
# ===============================
# Esta tabla representa códigos privados de canje.
# No son los códigos públicos tipo VIN-RAV4-2024.
# Son códigos entregados al comprador.

agregar_columna(cursor, "codigos_vehiculo", "vehiculo_id", "INTEGER")
agregar_columna(cursor, "codigos_vehiculo", "codigo", "TEXT")
agregar_columna(cursor, "codigos_vehiculo", "usado", "INTEGER DEFAULT 0")
agregar_columna(cursor, "codigos_vehiculo", "usado_por", "INTEGER")
agregar_columna(cursor, "codigos_vehiculo", "fecha_uso", "TEXT")
agregar_columna(cursor, "codigos_vehiculo", "creado_por", "INTEGER")
agregar_columna(cursor, "codigos_vehiculo", "creado_en", "TEXT")
agregar_columna(cursor, "codigos_vehiculo", "activo", "INTEGER DEFAULT 1")

# Código privado único.
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_codigo
    ON codigos_vehiculo(codigo)
""")

print("Índice único creado/verificado: idx_codigos_vehiculo_codigo")

# Evita tener más de un código activo y sin usar para el mismo vehículo.
# Si se pierde un código, primero se desactiva el anterior y luego se genera otro.
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_codigo_activo_unico_por_vehiculo
    ON codigos_vehiculo(vehiculo_id)
    WHERE activo = 1 AND usado = 0
""")

print("Índice único creado/verificado: idx_codigo_activo_unico_por_vehiculo")


# ===============================
# TABLA USUARIOS_VEHICULOS
# ===============================
# Aquí se guarda qué usuario reclamó qué vehículo.

agregar_columna(cursor, "usuarios_vehiculos", "codigo_vehiculo_id", "INTEGER")
agregar_columna(cursor, "usuarios_vehiculos", "kilometraje_inicial", "INTEGER DEFAULT 0")
agregar_columna(cursor, "usuarios_vehiculos", "fecha_registro", "TEXT")

# Como cada fila de vehiculos representa una unidad exacta,
# una unidad no debería quedar registrada por dos usuarios.
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unidad_vehiculo_registrada
    ON usuarios_vehiculos(vehiculo_id)
""")

print("Índice único creado/verificado: idx_unidad_vehiculo_registrada")

conexion.commit()
conexion.close()

print("Migración de códigos de canje completada correctamente.")