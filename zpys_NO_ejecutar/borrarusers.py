import sqlite3


#-----------ESTO BORRA TODA LA BASE DE DATOSS-------------
#676766767676767676767676767676767676767667667











conexion = sqlite3.connect("vinova.db")
cursor = conexion.cursor()

cursor.execute("DELETE FROM usuarios")

conexion.commit()
conexion.close()

print("Usuarios eliminados correctamente")