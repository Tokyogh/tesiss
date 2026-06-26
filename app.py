from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = "vinova"
app.permanent_session_lifetime = timedelta(days=1)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

#================= CONFIGURACIÓN DE CLOUDINARY =================
load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


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

    correo = request.form["email"].strip().lower()
    password = request.form["password"]

    conexion = sqlite3.connect("vinova.db")
    conexion.row_factory = sqlite3.Row
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

    if not check_password_hash(usuario["password"], password):
        flash("Contraseña incorrecta.")
        return redirect("/login")

    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["usuario"] = usuario["nombre"]
    session["rol"] = usuario["rol"]
    session["foto_perfil"] = usuario["foto_perfil"]

    return redirect("/perfil")

# ================= REGISTRO =================

@app.route("/register", methods=["POST"])
def register():

    nombre = request.form["nombre"].strip()
    correo = request.form["correo"].strip().lower()
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
        rol=session["rol"],
        foto_perfil=session.get("foto_perfil")
    )


# ================= FOTO DE PERFIL =================

@app.route("/perfil/foto", methods=["POST"])
@login_required
def actualizar_foto_perfil():

    if "foto_perfil" not in request.files:
        flash("No seleccionaste ninguna imagen.")
        return redirect("/perfil")

    archivo = request.files["foto_perfil"]

    if archivo.filename == "":
        flash("No seleccionaste ninguna imagen.")
        return redirect("/perfil")

    extensiones_permitidas = {"jpg", "jpeg", "png", "webp"}

    extension = archivo.filename.rsplit(".", 1)[-1].lower()

    if extension not in extensiones_permitidas:
        flash("Formato no permitido. Usa JPG, PNG o WEBP.")
        return redirect("/perfil")

    try:
        resultado = cloudinary.uploader.upload(
            archivo,
            folder="vinova/perfiles",
            public_id=f"usuario_{session['usuario_id']}_avatar",
            overwrite=True,
            invalidate=True,
            resource_type="image"
        )

        foto_url = cloudinary.CloudinaryImage(resultado["public_id"]).build_url(
            version=resultado.get("version"),
            width=300,
            height=300,
            crop="fill",
            gravity="face",
            quality="auto",
            fetch_format="auto",
            secure=True
        )

    except Exception:
        flash("No se pudo subir la imagen. Intenta nuevamente.")
        return redirect("/perfil")

    conexion = sqlite3.connect("vinova.db")
    cursor = conexion.cursor()

    cursor.execute(
        "UPDATE usuarios SET foto_perfil = ? WHERE id = ?",
        (foto_url, session["usuario_id"])
    )

    conexion.commit()
    conexion.close()

    session["foto_perfil"] = foto_url

    flash("Foto de perfil actualizada correctamente.")
    return redirect("/perfil")

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

#================= ERROR PESO =================
@app.errorhandler(413)
def archivo_demasiado_grande(error):
    flash("La imagen es demasiado pesada. Intenta con una imagen más pequeña.")
    return redirect("/perfil")

# ================= APP =================

if __name__ == "__main__":
    app.run(debug=True)