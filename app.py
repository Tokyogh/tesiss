from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "vinova"
app.permanent_session_lifetime = timedelta(days=1)

# ================= PROTEGER RUTAS =================

def login_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a tu perfil.")
            return redirect("/login")
        return ruta(*args, **kwargs)
    return wrapper

# ================= INICIO =================

@app.route("/")
def inicio():
    return render_template("index.html")

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        if "usuario_id" in session:
            return redirect("/perfil")

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

    session.permanent = True
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
@login_required
def perfil():

    return render_template(
        "profile.html",
        nombre=session["usuario"],
        rol=session["rol"]
    )

# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

# ================= CATALOG =================
# Catálogo público

@app.route("/catalog")
def catalog():

    return render_template("catalog.html")

# ================= APP =================

if __name__ == "__main__":
    app.run(debug=True)