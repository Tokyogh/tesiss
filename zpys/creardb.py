import sqlite3

conexion = sqlite3.connect("vinova.db")

cursor = conexion.cursor()
#-----------ESTO BORRA TODA LA BASE DE DATOSS-------------
#676766767676767676767676767676767676767667667










# ================= USUARIOS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'USUARIO'
)
""")

# ================= VEHICULOS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS vehiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marca TEXT NOT NULL,
    modelo TEXT NOT NULL,
    anio INTEGER NOT NULL,
    imagen TEXT,
    modelo_3d TEXT
)
""")

# ================= CODIGOS DE VEHICULO =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS codigos_vehiculo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    vehiculo_id INTEGER NOT NULL,
    usado INTEGER DEFAULT 0,
    
    FOREIGN KEY (vehiculo_id)
    REFERENCES vehiculos(id)
)
""")

# ================= USUARIOS_VEHICULOS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios_vehiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    vehiculo_id INTEGER NOT NULL,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (usuario_id)
    REFERENCES usuarios(id),

    FOREIGN KEY (vehiculo_id)
    REFERENCES vehiculos(id)
)
""")

conexion.commit()
conexion.close()

print("67")