import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "vinova.db"

print("=== Crear o convertir usuario a ADMIN ===")

nombre = input("Nombre del admin: ").strip()
correo = input("Correo del admin: ").strip().lower()
password = input("Contraseña del admin: ").strip()

if not nombre or not correo or not password:
    print("Nombre, correo y contraseña son obligatorios.")
    exit()

conexion = sqlite3.connect(DB_NAME)
conexion.row_factory = sqlite3.Row
cursor = conexion.cursor()

cursor.execute(
    "SELECT * FROM usuarios WHERE correo = ?",
    (correo,)
)

usuario = cursor.fetchone()

if usuario:
    cursor.execute(
        "UPDATE usuarios SET rol = ? WHERE correo = ?",
        ("ADMIN", correo)
    )

    print(f"El usuario {correo} ahora tiene rol ADMIN.")

else:
    password_hash = generate_password_hash(password)

    cursor.execute("""
        INSERT INTO usuarios (
            nombre,
            correo,
            password,
            rol
        )
        VALUES (?, ?, ?, ?)
    """, (
        nombre,
        correo,
        password_hash,
        "ADMIN"
    ))

    print(f"Administrador creado correctamente: {correo}")

conexion.commit()
conexion.close()