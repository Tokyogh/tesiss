import sqlite3

conexion = sqlite3.connect("vinova.db")
cursor = conexion.cursor()

try:
    cursor.execute("ALTER TABLE usuarios ADD COLUMN foto_perfil TEXT")
    conexion.commit()
    print("Columna foto_perfil agregada correctamente.")
except sqlite3.OperationalError as error:
    if "duplicate column name" in str(error).lower():
        print("La columna foto_perfil ya existe.")
    else:
        raise error
finally:
    conexion.close()
    