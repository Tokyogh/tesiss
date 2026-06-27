from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta, datetime
import os
import re
import secrets
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader


app = Flask(__name__)
app.secret_key = "vinova"
app.permanent_session_lifetime = timedelta(days=1)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# ================= CONFIGURACIÓN DE ARCHIVOS LOCALES =================
# Las imágenes de vehículos del catálogo se guardan localmente.
# Las fotos de perfil siguen usando Cloudinary.

app.config["VEHICLE_IMAGE_FOLDER"] = os.path.join(
    app.root_path,
    "static",
    "img",
    "vehicles"
)

app.config["VEHICLE_3D_FOLDER"] = os.path.join(
    app.root_path,
    "static",
    "models",
    "vehicles"
)

os.makedirs(app.config["VEHICLE_IMAGE_FOLDER"], exist_ok=True)
os.makedirs(app.config["VEHICLE_3D_FOLDER"], exist_ok=True)

EXTENSIONES_IMAGEN_VEHICULO = {"jpg", "jpeg", "png", "webp"}


# ================= CONFIGURACIÓN DE CLOUDINARY =================

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


# ================= FUNCIONES AUXILIARES =================

def conectar_db():
    conexion = sqlite3.connect("vinova.db")
    conexion.row_factory = sqlite3.Row
    return conexion


def extension_permitida(nombre_archivo, extensiones):
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in extensiones


def crear_slug(texto):
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = texto.strip("-")
    return texto or "vehiculo"


def generar_codigo_canje():
    """
    Genera un código privado de canje para entregar al comprador.
    Ejemplo: VNV-8F2K-91AD-Q7L2
    """

    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    bloque_1 = "".join(secrets.choice(caracteres) for _ in range(4))
    bloque_2 = "".join(secrets.choice(caracteres) for _ in range(4))
    bloque_3 = "".join(secrets.choice(caracteres) for _ in range(4))

    return f"VNV-{bloque_1}-{bloque_2}-{bloque_3}"


def guardar_imagen_vehiculo(archivo, codigo_catalogo):
    """
    Guarda la imagen del vehículo en:
    static/img/vehicles/

    En la base de datos se guarda la ruta relativa:
    img/vehicles/nombre-del-archivo.png
    """

    if not archivo or archivo.filename == "":
        return None

    if not extension_permitida(archivo.filename, EXTENSIONES_IMAGEN_VEHICULO):
        raise ValueError("Formato de imagen no permitido. Usa JPG, PNG o WEBP.")

    extension = archivo.filename.rsplit(".", 1)[1].lower()
    slug_codigo = crear_slug(codigo_catalogo)
    nombre_archivo = secure_filename(f"{slug_codigo}.{extension}")

    ruta_absoluta = os.path.join(app.config["VEHICLE_IMAGE_FOLDER"], nombre_archivo)
    archivo.save(ruta_absoluta)

    return f"img/vehicles/{nombre_archivo}"


# ================= PROTEGER RUTAS =================

def login_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a tu perfil.")
            return redirect("/login")
        return ruta(*args, **kwargs)
    return wrapper


def admin_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión.")
            return redirect("/login")

        if session.get("rol") != "ADMIN":
            flash("No tienes permisos para acceder al panel de administración.")
            return redirect("/perfil")

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

    conexion = conectar_db()
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

    conexion = conectar_db()
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

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            usuarios_vehiculos.*,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            vehiculos.tipo_vehiculo,
            vehiculos.combustible,
            vehiculos.transmision,
            vehiculos.kilometraje,
            vehiculos.precio,
            vehiculos.imagen,
            vehiculos.modelo_3d,
            vehiculos.modelo_3d_id,
            vehiculos.modelo_3d_tipo,
            vehiculos.descripcion,
            vehiculos.estado,
            codigos_vehiculo.codigo AS codigo_canje
        FROM usuarios_vehiculos
        INNER JOIN vehiculos
            ON vehiculos.id = usuarios_vehiculos.vehiculo_id
        LEFT JOIN codigos_vehiculo
            ON codigos_vehiculo.id = usuarios_vehiculos.codigo_vehiculo_id
        WHERE usuarios_vehiculos.usuario_id = ?
        ORDER BY usuarios_vehiculos.id DESC
    """, (
        session["usuario_id"],
    ))

    mis_vehiculos = cursor.fetchall()
    conexion.close()

    return render_template(
        "profile.html",
        nombre=session["usuario"],
        rol=session["rol"],
        foto_perfil=session.get("foto_perfil"),
        mis_vehiculos=mis_vehiculos
    )


# ================= CANJEAR CÓDIGO DE VEHÍCULO =================

@app.route("/perfil/vehiculo/agregar", methods=["POST"])
@login_required
def canjear_codigo_vehiculo():

    codigo_ingresado = (
        request.form.get("codigo_vehiculo")
        or request.form.get("codigo_canje")
        or request.form.get("codigo")
        or ""
    ).strip().upper()

    if not codigo_ingresado:
        flash("Ingresa el código de activación del vehículo.")
        return redirect("/perfil")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            SELECT
                codigos_vehiculo.*,
                vehiculos.id AS vehiculo_id_real,
                vehiculos.codigo_catalogo,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio,
                vehiculos.kilometraje,
                vehiculos.estado AS estado_vehiculo,
                vehiculos.activo AS vehiculo_activo
            FROM codigos_vehiculo
            INNER JOIN vehiculos
                ON vehiculos.id = codigos_vehiculo.vehiculo_id
            WHERE codigos_vehiculo.codigo = ?
            LIMIT 1
        """, (
            codigo_ingresado,
        ))

        codigo = cursor.fetchone()

        if not codigo:
            conexion.rollback()
            flash("Código inválido. Verifica el código entregado por la concesionaria.")
            return redirect("/perfil")

        if codigo["activo"] != 1:
            conexion.rollback()
            flash("Este código está inactivo. Contacta con la concesionaria.")
            return redirect("/perfil")

        if codigo["usado"] == 1:
            conexion.rollback()
            flash("Este código ya fue utilizado.")
            return redirect("/perfil")

        if codigo["vehiculo_activo"] != 1 or codigo["estado_vehiculo"] == "Vendido":
            conexion.rollback()
            flash("Este vehículo ya no está disponible para registro.")
            return redirect("/perfil")

        vehiculo_id = codigo["vehiculo_id_real"]

        cursor.execute("""
            SELECT id
            FROM usuarios_vehiculos
            WHERE vehiculo_id = ?
            LIMIT 1
        """, (
            vehiculo_id,
        ))

        vehiculo_ya_registrado = cursor.fetchone()

        if vehiculo_ya_registrado:
            conexion.rollback()
            flash("Este vehículo ya fue registrado por otro usuario.")
            return redirect("/perfil")

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO usuarios_vehiculos (
                usuario_id,
                vehiculo_id,
                codigo_vehiculo_id,
                kilometraje_inicial,
                fecha_registro
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["usuario_id"],
            vehiculo_id,
            codigo["id"],
            codigo["kilometraje"] or 0,
            ahora
        ))

        cursor.execute("""
            UPDATE codigos_vehiculo
            SET
                usado = 1,
                usado_por = ?,
                fecha_uso = ?
            WHERE id = ?
        """, (
            session["usuario_id"],
            ahora,
            codigo["id"]
        ))

        cursor.execute("""
            UPDATE vehiculos
            SET
                activo = 0,
                estado = 'Vendido',
                actualizado_en = ?
            WHERE id = ?
        """, (
            ahora,
            vehiculo_id
        ))

        conexion.commit()

        flash(
            f"Vehículo registrado correctamente: "
            f"{codigo['marca']} {codigo['modelo']} {codigo['anio']}."
        )

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Este vehículo ya fue registrado anteriormente.")

    except Exception as error:
        conexion.rollback()
        print("Error al canjear código de vehículo:", error)
        flash("No se pudo registrar el vehículo. Intenta nuevamente.")

    finally:
        conexion.close()

    return redirect("/perfil")


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

    except Exception as error:
        print("Error al subir imagen a Cloudinary:", error)
        flash("No se pudo subir la imagen. Intenta nuevamente.")
        return redirect("/perfil")

    conexion = conectar_db()
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

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM vehiculos
        WHERE activo = 1
        ORDER BY id DESC
    """)
    vehiculos = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM vehiculos WHERE activo = 1")
    total_vehiculos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 1 AND tipo_vehiculo IN ('SUV', 'Suv', 'suv')
    """)
    total_suv = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 1 AND tipo_vehiculo IN ('Camioneta', 'Pickup')
    """)
    total_camionetas = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 1 AND combustible IN ('Híbrido', 'Eléctrico')
    """)
    total_hibridos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 1 AND estado = 'Disponible'
    """)
    total_disponibles = cursor.fetchone()[0]

    conexion.close()

    return render_template(
        "catalog.html",
        vehiculos=vehiculos,
        total_vehiculos=total_vehiculos,
        total_suv=total_suv,
        total_camionetas=total_camionetas,
        total_hibridos=total_hibridos,
        total_disponibles=total_disponibles
    )


# ================= ADMIN =================

@app.route("/admin")
@login_required
@admin_required
def admin_inicio():
    return redirect("/admin/vehiculos")


@app.route("/admin/vehiculos")
@login_required
@admin_required
def admin_vehiculos():

    editar_id = request.args.get("editar", type=int)

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM vehiculos
        ORDER BY id DESC
    """)

    vehiculos = cursor.fetchall()

    vehiculo_editar = None

    if editar_id:
        cursor.execute(
            "SELECT * FROM vehiculos WHERE id = ?",
            (editar_id,)
        )
        vehiculo_editar = cursor.fetchone()

    cursor.execute("""
        SELECT
            codigos_vehiculo.*,
            usuarios.nombre AS usado_por_nombre
        FROM codigos_vehiculo
        LEFT JOIN usuarios
            ON usuarios.id = codigos_vehiculo.usado_por
        ORDER BY codigos_vehiculo.id DESC
    """)

    codigos = cursor.fetchall()

    codigos_por_vehiculo = {}

    for codigo in codigos:
        vehiculo_id = codigo["vehiculo_id"]

        if vehiculo_id not in codigos_por_vehiculo:
            codigos_por_vehiculo[vehiculo_id] = []

        codigos_por_vehiculo[vehiculo_id].append(codigo)

    cursor.execute("SELECT COUNT(*) FROM vehiculos")
    total_vehiculos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vehiculos WHERE activo = 1")
    vehiculos_activos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vehiculos WHERE activo = 0")
    vehiculos_inactivos = cursor.fetchone()[0]

    conexion.close()

    return render_template(
        "admin.html",
        vehiculos=vehiculos,
        vehiculo_editar=vehiculo_editar,
        total_vehiculos=total_vehiculos,
        vehiculos_activos=vehiculos_activos,
        vehiculos_inactivos=vehiculos_inactivos,
        codigos_por_vehiculo=codigos_por_vehiculo
    )


@app.route("/admin/vehiculos/guardar", methods=["POST"])
@login_required
@admin_required
def admin_guardar_vehiculo():

    vehiculo_id = request.form.get("vehiculo_id", "").strip()

    codigo_catalogo = request.form.get("codigo_catalogo", "").strip().upper()
    marca = request.form.get("marca", "").strip()
    modelo = request.form.get("modelo", "").strip()
    anio = request.form.get("anio", "").strip()
    tipo_vehiculo = request.form.get("tipo_vehiculo", "").strip()
    combustible = request.form.get("combustible", "").strip()
    transmision = request.form.get("transmision", "").strip()
    kilometraje = request.form.get("kilometraje", "0").strip()
    precio = request.form.get("precio", "0").strip()
    estado = request.form.get("estado", "Disponible").strip()
    descripcion = request.form.get("descripcion", "").strip()
    modelo_3d_id = request.form.get("modelo_3d_id", "").strip()
    modelo_3d = request.form.get("modelo_3d", "").strip()
    modelo_3d_tipo = request.form.get("modelo_3d_tipo", "glb").strip()

    activo = 1 if request.form.get("activo") == "on" else 0

    if not codigo_catalogo or not marca or not modelo or not anio:
        flash("Código, marca, modelo y año son obligatorios.")
        return redirect("/admin/vehiculos")

    try:
        anio = int(anio)
        kilometraje = int(kilometraje or 0)
        precio = float(precio or 0)
    except ValueError:
        flash("Año, kilometraje y precio deben ser valores numéricos.")
        return redirect("/admin/vehiculos")

    archivo_imagen = request.files.get("imagen")

    try:
        imagen_guardada = guardar_imagen_vehiculo(archivo_imagen, codigo_catalogo)
    except ValueError as error:
        flash(str(error))
        return redirect("/admin/vehiculos")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if vehiculo_id:
            vehiculo_id = int(vehiculo_id)

            if imagen_guardada:
                cursor.execute("""
                    UPDATE vehiculos
                    SET
                        codigo_catalogo = ?,
                        marca = ?,
                        modelo = ?,
                        anio = ?,
                        tipo_vehiculo = ?,
                        combustible = ?,
                        transmision = ?,
                        kilometraje = ?,
                        precio = ?,
                        imagen = ?,
                        modelo_3d = ?,
                        modelo_3d_id = ?,
                        modelo_3d_tipo = ?,
                        descripcion = ?,
                        estado = ?,
                        activo = ?,
                        actualizado_en = ?
                    WHERE id = ?
                """, (
                    codigo_catalogo,
                    marca,
                    modelo,
                    anio,
                    tipo_vehiculo,
                    combustible,
                    transmision,
                    kilometraje,
                    precio,
                    imagen_guardada,
                    modelo_3d,
                    modelo_3d_id,
                    modelo_3d_tipo,
                    descripcion,
                    estado,
                    activo,
                    ahora,
                    vehiculo_id
                ))

            else:
                cursor.execute("""
                    UPDATE vehiculos
                    SET
                        codigo_catalogo = ?,
                        marca = ?,
                        modelo = ?,
                        anio = ?,
                        tipo_vehiculo = ?,
                        combustible = ?,
                        transmision = ?,
                        kilometraje = ?,
                        precio = ?,
                        modelo_3d = ?,
                        modelo_3d_id = ?,
                        modelo_3d_tipo = ?,
                        descripcion = ?,
                        estado = ?,
                        activo = ?,
                        actualizado_en = ?
                    WHERE id = ?
                """, (
                    codigo_catalogo,
                    marca,
                    modelo,
                    anio,
                    tipo_vehiculo,
                    combustible,
                    transmision,
                    kilometraje,
                    precio,
                    modelo_3d,
                    modelo_3d_id,
                    modelo_3d_tipo,
                    descripcion,
                    estado,
                    activo,
                    ahora,
                    vehiculo_id
                ))

            flash("Vehículo actualizado correctamente.")

        else:
            cursor.execute("""
                INSERT INTO vehiculos (
                    codigo_catalogo,
                    marca,
                    modelo,
                    anio,
                    tipo_vehiculo,
                    combustible,
                    transmision,
                    kilometraje,
                    precio,
                    imagen,
                    modelo_3d,
                    modelo_3d_id,
                    modelo_3d_tipo,
                    descripcion,
                    estado,
                    activo,
                    creado_por,
                    creado_en
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo_catalogo,
                marca,
                modelo,
                anio,
                tipo_vehiculo,
                combustible,
                transmision,
                kilometraje,
                precio,
                imagen_guardada,
                modelo_3d,
                modelo_3d_id,
                modelo_3d_tipo,
                descripcion,
                estado,
                activo,
                session["usuario_id"],
                ahora
            ))

            flash("Vehículo creado correctamente.")

        conexion.commit()

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe un vehículo con ese código de catálogo.")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar vehículo:", error)
        flash("No se pudo guardar el vehículo. Revisa los datos e intenta nuevamente.")

    finally:
        conexion.close()

    return redirect("/admin/vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/estado", methods=["POST"])
@login_required
@admin_required
def admin_cambiar_estado_vehiculo(vehiculo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT activo FROM vehiculos WHERE id = ?",
        (vehiculo_id,)
    )

    vehiculo = cursor.fetchone()

    if not vehiculo:
        conexion.close()
        flash("Vehículo no encontrado.")
        return redirect("/admin/vehiculos")

    nuevo_estado = 0 if vehiculo["activo"] == 1 else 1

    cursor.execute("""
        UPDATE vehiculos
        SET activo = ?, actualizado_en = ?
        WHERE id = ?
    """, (
        nuevo_estado,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        vehiculo_id
    ))

    conexion.commit()
    conexion.close()

    flash("Estado del vehículo actualizado.")
    return redirect("/admin/vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/codigo/generar", methods=["POST"])
@login_required
@admin_required
def admin_generar_codigo_vehiculo(vehiculo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM vehiculos WHERE id = ?",
        (vehiculo_id,)
    )

    vehiculo = cursor.fetchone()

    if not vehiculo:
        conexion.close()
        flash("Vehículo no encontrado.")
        return redirect("/admin/vehiculos")

    cursor.execute("""
        SELECT *
        FROM codigos_vehiculo
        WHERE vehiculo_id = ?
          AND usado = 0
          AND activo = 1
        LIMIT 1
    """, (
        vehiculo_id,
    ))

    codigo_existente = cursor.fetchone()

    if codigo_existente:
        conexion.close()
        flash(f"Este vehículo ya tiene un código activo: {codigo_existente['codigo']}")
        return redirect("/admin/vehiculos")

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        codigo_generado = None

        for intento in range(20):
            codigo_generado = generar_codigo_canje()

            try:
                cursor.execute("""
                    INSERT INTO codigos_vehiculo (
                        vehiculo_id,
                        codigo,
                        usado,
                        usado_por,
                        fecha_uso,
                        creado_por,
                        creado_en,
                        activo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    vehiculo_id,
                    codigo_generado,
                    0,
                    None,
                    None,
                    session["usuario_id"],
                    ahora,
                    1
                ))

                conexion.commit()
                flash(f"Código de canje generado: {codigo_generado}")
                break

            except sqlite3.IntegrityError:
                conexion.rollback()
                codigo_generado = None

        if not codigo_generado:
            flash("No se pudo generar un código único. Intenta nuevamente.")

    except Exception as error:
        conexion.rollback()
        print("Error al generar código de canje:", error)
        flash("No se pudo generar el código de canje.")

    finally:
        conexion.close()

    return redirect("/admin/vehiculos")


@app.route("/admin/codigos/<int:codigo_id>/desactivar", methods=["POST"])
@login_required
@admin_required
def admin_desactivar_codigo_vehiculo(codigo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM codigos_vehiculo WHERE id = ?",
        (codigo_id,)
    )

    codigo = cursor.fetchone()

    if not codigo:
        conexion.close()
        flash("Código no encontrado.")
        return redirect("/admin/vehiculos")

    if codigo["usado"] == 1:
        conexion.close()
        flash("No puedes desactivar un código que ya fue usado.")
        return redirect("/admin/vehiculos")

    cursor.execute("""
        UPDATE codigos_vehiculo
        SET activo = 0
        WHERE id = ?
    """, (
        codigo_id,
    ))

    conexion.commit()
    conexion.close()

    flash("Código de canje desactivado correctamente.")
    return redirect("/admin/vehiculos")


# ================= ERROR PESO =================

@app.errorhandler(413)
def archivo_demasiado_grande(error):
    flash("La imagen es demasiado pesada. Intenta con una imagen más pequeña.")
    return redirect(request.referrer or "/perfil")


# ================= APP =================

if __name__ == "__main__":
    app.run(debug=True)