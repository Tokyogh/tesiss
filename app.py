from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "vinova"

# ================= INICIO =================

@app.route("/")
def inicio():
    return render_template("index.html")

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    correo = request.form["email"]
    password = request.form["password"]

    conexion = sqlite3.connect("vinova.db")
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,)
    )

    usuario = cursor.fetchone()

    conexion.close()

    if not usuario:

        flash("Usuario no encontrado.")
        return redirect("/login")

    if not check_password_hash(usuario[3], password):

        flash("Contraseña incorrecta.")
        return redirect("/login")

    session["usuario_id"] = usuario[0]
    session["usuario"] = usuario[1]
    session["rol"] = usuario[4]

    return redirect("/perfil")

# ================= REGISTRO =================

@app.route("/register", methods=["POST"])
def register():

    nombre = request.form["nombre"]
    correo = request.form["correo"]
    password = request.form["password"]

    conexion = sqlite3.connect("vinova.db")
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,)
    )

    if cursor.fetchone():

        conexion.close()

        flash("Este correo ya está registrado.")
        return redirect("/login")

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
        "USUARIO"
    ))

    conexion.commit()
    conexion.close()

    flash("Cuenta creada correctamente.")

    return redirect("/login")

# ================= PERFIL =================

@app.route("/perfil")
def perfil():

    if "usuario" not in session:
        return redirect("/login")

    return render_template(
        "profile.html",
        nombre=session["usuario"]
    )

# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

# ================= APP =================

if __name__ == "__main__":
    app.run(debug=True)