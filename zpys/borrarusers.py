import sqlite3

conexion = sqlite3.connect("vinova.db")
cursor = conexion.cursor()

cursor.execute("DELETE FROM usuarios")

conexion.commit()
conexion.close()

print("Usuarios eliminados correctamente")