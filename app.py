from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta, datetime
import os
import re
import secrets
import time
import html
from dotenv import load_dotenv
from markupsafe import Markup
import cloudinary
import cloudinary.uploader


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "vinova")
app.permanent_session_lifetime = timedelta(days=1)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_COOKIE_SECURE", "0") == "1"


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


# ================= SEGURIDAD BÁSICA =================
# CSRF se valida en todos los formularios POST.
# El token se inyecta automáticamente en respuestas HTML para no tener que
# editar todos los templates existentes.

CSRF_FORM_FIELD = "csrf_token"

# Rate limit simple en memoria para login. Para producción con varios procesos
# conviene mover esto a Redis o una tabla dedicada.
LOGIN_ATTEMPTS = {}
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
LOGIN_LOCK_SECONDS = int(os.getenv("LOGIN_LOCK_SECONDS", "900"))

ROLES_CREABLES_DESDE_PANEL = {"USUARIO", "TRABAJADOR"}


# ================= CONFIGURACIÓN DE CLOUDINARY =================

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


def normalizar_kilometraje(valor):
    """
    Convierte el kilometraje a entero antes de enviarlo a los templates.

    Acepta valores como:
    - 55430
    - "55430"
    - "55.430"
    - "55,430"
    - "55 430 km"

    Devuelve None si el valor está vacío, no es numérico o es negativo.
    """

    if valor is None:
        return None

    if isinstance(valor, int):
        return valor if valor >= 0 else None

    if isinstance(valor, float):
        return int(valor) if valor >= 0 else None

    texto = str(valor).strip().lower()

    if not texto:
        return None

    texto = texto.replace("kilómetros", "")
    texto = texto.replace("kilometros", "")
    texto = texto.replace("kms", "")
    texto = texto.replace("km", "")
    texto = re.sub(r"\s+", "", texto)

    # Para kilometraje usamos enteros. Quitamos separadores de miles comunes.
    texto = texto.replace(".", "").replace(",", "")

    if not re.fullmatch(r"\d+", texto):
        return None

    return int(texto)


def normalizar_precio(valor):
    """
    Convierte precios escritos con separadores comunes a float.

    Acepta valores como:
    - 28900
    - "28900"
    - "28,900"
    - "28.900"
    - "28,900.50"
    - "28.900,50"

    Devuelve None si el valor está vacío, no es numérico o es negativo.
    """

    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        precio = float(valor)
        return precio if precio >= 0 else None

    texto = str(valor).strip().lower()

    if not texto:
        return None

    texto = texto.replace("$", "")
    texto = texto.replace("usd", "")
    texto = texto.replace("dólares", "")
    texto = texto.replace("dolares", "")
    texto = re.sub(r"\s+", "", texto)

    if "," in texto and "." in texto:
        # Si la coma aparece después del punto, asumimos formato latino:
        # 28.900,50 -> 28900.50
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            # 28,900.50 -> 28900.50
            texto = texto.replace(",", "")

    elif "," in texto:
        partes = texto.split(",")

        if len(partes) == 2 and len(partes[1]) == 3 and partes[0].isdigit() and partes[1].isdigit():
            texto = "".join(partes)
        else:
            texto = texto.replace(",", ".")

    elif "." in texto:
        partes = texto.split(".")

        if len(partes) == 2 and len(partes[1]) == 3 and partes[0].isdigit() and partes[1].isdigit():
            texto = "".join(partes)

    try:
        precio = float(texto)
    except ValueError:
        return None

    return precio if precio >= 0 else None


def obtener_nombre_imagen_vehiculo(ruta_imagen):
    """
    Normaliza la imagen del vehículo para profile.html.

    En la base puede venir como:
    - img/vehicles/archivo.webp
    - static/img/vehicles/archivo.webp
    - archivo.webp

    profile.html ya antepone:
    url_for('static', filename='img/vehicles/' ~ vehiculo.imagen)

    Por eso aquí devolvemos solo el nombre del archivo.
    """

    if not ruta_imagen:
        return None

    ruta_limpia = str(ruta_imagen).strip().replace("\\", "/")

    if not ruta_limpia:
        return None

    return os.path.basename(ruta_limpia)


def ejecutar_sql_seguro(cursor, sql, descripcion="operación SQL"):
    """
    Ejecuta SQL de mantenimiento sin romper el arranque si ya existen datos
    duplicados. Esto es útil para índices UNIQUE en bases antiguas.
    """

    try:
        cursor.execute(sql)
    except sqlite3.IntegrityError as error:
        print(f"Advertencia: no se pudo aplicar {descripcion}: {error}")


def agregar_columna_si_falta(cursor, tabla, columna, definicion):
    cursor.execute(f"PRAGMA table_info({tabla})")
    columnas = {fila[1] for fila in cursor.fetchall()}

    if columna not in columnas:
        cursor.execute(
            f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
        )


def tabla_existe(cursor, nombre_tabla):
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, (
        nombre_tabla,
    ))

    return cursor.fetchone() is not None


def asegurar_migraciones_admin():
    """
    Asegura estructuras administrativas sin romper bases existentes.

    Incluye:
    - Archivado de vehículos.
    - Auditoría de canjes reversados.
    - Estado activo/fechas para usuarios.
    - Índices UNIQUE para datos críticos cuando no existen duplicados previos.
    """

    conexion = sqlite3.connect("vinova.db")
    cursor = conexion.cursor()

    if tabla_existe(cursor, "vehiculos"):
        columnas_vehiculos = {
            "archivado": "INTEGER DEFAULT 0",
            "archivado_en": "TEXT",
            "archivado_por": "INTEGER",
            "motivo_archivado": "TEXT",
            "actualizado_en": "TEXT"
        }

        for columna, definicion in columnas_vehiculos.items():
            agregar_columna_si_falta(cursor, "vehiculos", columna, definicion)

        ejecutar_sql_seguro(
            cursor,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_codigo_catalogo_unico
            ON vehiculos(codigo_catalogo)
            WHERE codigo_catalogo IS NOT NULL AND TRIM(codigo_catalogo) != ''
            """,
            "índice único de código de catálogo"
        )

    if tabla_existe(cursor, "codigos_vehiculo"):
        ejecutar_sql_seguro(
            cursor,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_codigo_unico
            ON codigos_vehiculo(codigo)
            WHERE codigo IS NOT NULL AND TRIM(codigo) != ''
            """,
            "índice único de código de canje"
        )

        ejecutar_sql_seguro(
            cursor,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_codigos_vehiculo_un_codigo_por_vehiculo
            ON codigos_vehiculo(vehiculo_id)
            WHERE vehiculo_id IS NOT NULL
            """,
            "índice único de un código por vehículo"
        )

    if tabla_existe(cursor, "usuarios"):
        columnas_usuarios = {
            "activo": "INTEGER DEFAULT 1",
            "creado_en": "TEXT",
            "actualizado_en": "TEXT"
        }

        for columna, definicion in columnas_usuarios.items():
            agregar_columna_si_falta(cursor, "usuarios", columna, definicion)

        ejecutar_sql_seguro(
            cursor,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_correo_unico
            ON usuarios(correo)
            WHERE correo IS NOT NULL AND TRIM(correo) != ''
            """,
            "índice único de correo de usuario"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS canjes_reversados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_vehiculo_id INTEGER,
            usuario_id INTEGER,
            vehiculo_id INTEGER,
            codigo_vehiculo_id INTEGER,
            codigo_canje TEXT,
            usuario_nombre TEXT,
            usuario_correo TEXT,
            vehiculo_referencia TEXT,
            vehiculo_descripcion TEXT,
            kilometraje_inicial INTEGER,
            fecha_registro_original TEXT,
            reversado_por INTEGER,
            reversado_en TEXT,
            motivo TEXT
        )
    """)

    conexion.commit()
    conexion.close()

def fecha_actual():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def redirigir_admin(seccion="vehiculos"):
    return redirect(f"/admin/vehiculos#admin-{seccion}")


def tiene_canje_real(cursor, vehiculo_id):
    """
    Un vehículo tiene canje real cuando ya existe en usuarios_vehiculos.
    Eso significa que fue agregado al perfil de un usuario mediante el flujo
    de canje y no debe reactivarse con el botón normal.
    """

    cursor.execute("""
        SELECT COUNT(*)
        FROM usuarios_vehiculos
        WHERE vehiculo_id = ?
    """, (
        vehiculo_id,
    ))

    return cursor.fetchone()[0] > 0


def validar_codigo_reactivable(cursor, codigo_id):
    """
    Valida que un código inactivo pueda volver a estar disponible.

    Solo se permite reactivar si:
    - El código existe.
    - No fue usado.
    - Está inactivo.
    - El vehículo existe, no está vendido, no está archivado y está activo.
    - El vehículo no está registrado actualmente en el perfil de ningún usuario.
    """

    cursor.execute("""
        SELECT
            codigos_vehiculo.*,
            vehiculos.id AS vehiculo_id_real,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            vehiculos.activo AS vehiculo_activo,
            COALESCE(NULLIF(TRIM(vehiculos.estado), ''), 'Disponible') AS estado_vehiculo,
            COALESCE(vehiculos.archivado, 0) AS vehiculo_archivado
        FROM codigos_vehiculo
        LEFT JOIN vehiculos
            ON vehiculos.id = codigos_vehiculo.vehiculo_id
        WHERE codigos_vehiculo.id = ?
        LIMIT 1
    """, (
        codigo_id,
    ))

    codigo = cursor.fetchone()

    if not codigo:
        return None, "Código no encontrado."

    if codigo["usado"] == 1:
        return None, "No puedes reactivar un código que ya fue usado. Si fue un error, primero reversa/anula el canje desde administración."

    if codigo["activo"] == 1:
        return None, "Este código ya está activo."

    if not codigo["vehiculo_id_real"]:
        return None, "El código no tiene un vehículo válido asociado."

    if codigo["vehiculo_archivado"] == 1:
        return None, "No puedes reactivar el código de un vehículo archivado."

    if codigo["estado_vehiculo"] == "Vendido":
        return None, "No puedes reactivar el código de un vehículo vendido."

    if codigo["vehiculo_activo"] != 1:
        return None, "El vehículo debe estar activo para reactivar el código."

    if tiene_canje_real(cursor, codigo["vehiculo_id_real"]):
        return None, "Este vehículo ya está registrado en un perfil. No se puede reactivar su código."

    return codigo, None


def reactivar_codigo_vehiculo_seguro(cursor, codigo_id):
    codigo, error = validar_codigo_reactivable(cursor, codigo_id)

    if error:
        return None, error

    cursor.execute("""
        UPDATE codigos_vehiculo
        SET activo = 1
        WHERE id = ?
    """, (
        codigo_id,
    ))

    return codigo, None


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



# ================= CSRF =================

def obtener_csrf_token():
    token = session.get(CSRF_FORM_FIELD)

    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_FORM_FIELD] = token

    return token


def crear_csrf_input():
    token = html.escape(obtener_csrf_token(), quote=True)
    return Markup(
        f'<input type="hidden" name="{CSRF_FORM_FIELD}" value="{token}">'
    )


@app.context_processor
def contexto_csrf():
    return {
        "csrf_token": obtener_csrf_token,
        "csrf_input": crear_csrf_input
    }


@app.before_request
def validar_csrf_en_post():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    token_sesion = session.get(CSRF_FORM_FIELD)
    token_enviado = (
        request.form.get(CSRF_FORM_FIELD)
        or request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
    )

    if not token_sesion or not token_enviado:
        flash("La solicitud expiró o no es válida. Intenta nuevamente.", "error")
        return redirect(request.referrer or url_for("inicio"))

    if not secrets.compare_digest(str(token_sesion), str(token_enviado)):
        flash("La solicitud no pudo verificarse por seguridad. Intenta nuevamente.", "error")
        return redirect(request.referrer or url_for("inicio"))

    return None


@app.after_request
def inyectar_csrf_en_formularios(response):
    if request.method != "GET":
        return response

    content_type = response.headers.get("Content-Type", "")

    if "text/html" not in content_type.lower():
        return response

    if response.direct_passthrough:
        return response

    try:
        contenido = response.get_data(as_text=True)
    except RuntimeError:
        return response

    patron_form_post = re.compile(
        r'(<form\b(?=[^>]*\bmethod=["\']?post["\']?)[^>]*>)',
        re.IGNORECASE
    )

    if not patron_form_post.search(contenido):
        return response

    token = html.escape(obtener_csrf_token(), quote=True)
    campo_csrf = f'\n    <input type="hidden" name="{CSRF_FORM_FIELD}" value="{token}">'

    contenido = patron_form_post.sub(r'\1' + campo_csrf, contenido)
    response.set_data(contenido)
    response.headers["Content-Length"] = str(len(response.get_data()))

    return response


# ================= RATE LIMIT LOGIN =================

def obtener_ip_cliente():
    forwarded_for = request.headers.get("X-Forwarded-For", "")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.remote_addr or "desconocida"


def clave_rate_login(correo):
    correo_normalizado = (correo or "").strip().lower()
    return f"{obtener_ip_cliente()}:{correo_normalizado}"


def segundos_bloqueo_login(correo):
    clave = clave_rate_login(correo)
    registro = LOGIN_ATTEMPTS.get(clave)
    ahora = time.time()

    if not registro:
        return 0

    bloqueado_hasta = registro.get("bloqueado_hasta", 0)

    if bloqueado_hasta > ahora:
        return int(bloqueado_hasta - ahora)

    if ahora - registro.get("inicio", ahora) > LOGIN_WINDOW_SECONDS:
        LOGIN_ATTEMPTS.pop(clave, None)

    return 0


def registrar_login_fallido(correo):
    clave = clave_rate_login(correo)
    ahora = time.time()
    registro = LOGIN_ATTEMPTS.get(clave)

    if not registro or ahora - registro.get("inicio", ahora) > LOGIN_WINDOW_SECONDS:
        LOGIN_ATTEMPTS[clave] = {
            "intentos": 1,
            "inicio": ahora,
            "bloqueado_hasta": 0
        }
        return

    registro["intentos"] += 1

    if registro["intentos"] >= LOGIN_MAX_ATTEMPTS:
        registro["bloqueado_hasta"] = ahora + LOGIN_LOCK_SECONDS


def limpiar_login_fallido(correo):
    LOGIN_ATTEMPTS.pop(clave_rate_login(correo), None)


def usuario_es_ultimo_admin_activo(cursor, usuario_id):
    cursor.execute("""
        SELECT rol, COALESCE(activo, 1) AS activo
        FROM usuarios
        WHERE id = ?
    """, (
        usuario_id,
    ))

    usuario = cursor.fetchone()

    if not usuario or usuario["rol"] != "ADMIN" or usuario["activo"] != 1:
        return False

    cursor.execute("""
        SELECT COUNT(*)
        FROM usuarios
        WHERE rol = 'ADMIN'
          AND COALESCE(activo, 1) = 1
    """)

    return cursor.fetchone()[0] <= 1


# ================= PROTEGER RUTAS =================

def login_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a tu perfil.", "info")
            return redirect("/login")
        return ruta(*args, **kwargs)
    return wrapper


def admin_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión.", "info")
            return redirect("/login")

        if session.get("rol") != "ADMIN":
            flash("No tienes permisos para acceder al panel de administración.", "warning")
            return redirect("/perfil")

        return ruta(*args, **kwargs)
    return wrapper

def personal_required(ruta):
    @wraps(ruta)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión.", "info")
            return redirect("/login")

        rol = str(session.get("rol", "")).upper()

        if rol not in {"ADMIN", "TRABAJADOR"}:
            flash("No tienes permisos para acceder al panel operativo.", "warning")
            return redirect("/perfil")

        return ruta(*args, **kwargs)

    return wrapper


@app.context_processor
def contexto_panel_trabajador():
    panel_url = ""
    rol_actual = str(session.get("rol", "")).upper()

    if rol_actual in {"ADMIN", "TRABAJADOR"}:
        try:
            panel_url = url_for("trabajador_panel")
        except Exception:
            panel_url = ""

    return {
        "trabajador_panel_url": panel_url
    }


@app.route("/trabajador")
@login_required
@personal_required
def trabajador_panel():

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            vehiculos.*,
            codigos_vehiculo.codigo AS codigo_canje,
            codigos_vehiculo.usado AS codigo_usado,
            codigos_vehiculo.activo AS codigo_activo
        FROM vehiculos
        LEFT JOIN codigos_vehiculo
            ON codigos_vehiculo.vehiculo_id = vehiculos.id
        WHERE COALESCE(vehiculos.archivado, 0) = 0
        ORDER BY vehiculos.id DESC
    """)
    vehiculos = cursor.fetchall()

    cursor.execute("""
        SELECT
            codigos_vehiculo.*,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            usuarios.nombre AS usado_por_nombre
        FROM codigos_vehiculo
        INNER JOIN vehiculos
            ON vehiculos.id = codigos_vehiculo.vehiculo_id
        LEFT JOIN usuarios
            ON usuarios.id = codigos_vehiculo.usado_por
        ORDER BY codigos_vehiculo.id DESC
    """)
    codigos = cursor.fetchall()

    cursor.execute("""
        SELECT
            usuarios_vehiculos.id,
            usuarios_vehiculos.fecha_registro,
            usuarios_vehiculos.kilometraje_inicial,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            codigos_vehiculo.codigo AS codigo_canje
        FROM usuarios_vehiculos
        INNER JOIN usuarios
            ON usuarios.id = usuarios_vehiculos.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = usuarios_vehiculos.vehiculo_id
        LEFT JOIN codigos_vehiculo
            ON codigos_vehiculo.id = usuarios_vehiculos.codigo_vehiculo_id
        ORDER BY usuarios_vehiculos.id DESC
    """)
    ventas_canje = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 0
    """)
    total_vehiculos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 0
          AND activo = 1
          AND COALESCE(NULLIF(TRIM(estado), ''), 'Disponible') = 'Disponible'
    """)
    vehiculos_disponibles = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 0
          AND COALESCE(NULLIF(TRIM(estado), ''), 'Disponible') = 'Reservado'
    """)
    vehiculos_reservados = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM codigos_vehiculo
        WHERE activo = 1
          AND usado = 0
    """)
    codigos_disponibles = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM usuarios_vehiculos
    """)
    total_canjes = cursor.fetchone()[0]

    conexion.close()

    return render_template(
        "trabajador.html",
        vehiculos=vehiculos,
        codigos=codigos,
        ventas_canje=ventas_canje,
        total_vehiculos=total_vehiculos,
        vehiculos_disponibles=vehiculos_disponibles,
        vehiculos_reservados=vehiculos_reservados,
        codigos_disponibles=codigos_disponibles,
        total_canjes=total_canjes,
        trabajador_generar_codigo_url="/trabajador/vehiculos/__ID__/codigo/generar",
        trabajador_archivar_vehiculo_url="/trabajador/vehiculos/__ID__/archivar",
        trabajador_reactivar_codigo_url="/trabajador/codigos/__ID__/reactivar"
    )


@app.route("/trabajador/vehiculos/<int:vehiculo_id>/codigo/generar", methods=["POST"])
@login_required
@personal_required
def trabajador_generar_codigo_vehiculo(vehiculo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            *,
            COALESCE(archivado, 0) AS archivado_normalizado
        FROM vehiculos
        WHERE id = ?
    """, (
        vehiculo_id,
    ))
    vehiculo = cursor.fetchone()

    if not vehiculo:
        conexion.close()
        flash("Vehículo no encontrado.", "warning")
        return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

    if vehiculo["archivado_normalizado"] == 1:
        conexion.close()
        flash("No se puede generar código para un vehículo archivado.", "warning")
        return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

    if vehiculo["estado"] == "Vendido":
        conexion.close()
        flash("No se puede generar código para un vehículo vendido.", "warning")
        return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

    if vehiculo["activo"] != 1:
        conexion.close()
        flash("El vehículo debe estar activo para generar un código.", "warning")
        return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

    cursor.execute("""
        SELECT *
        FROM codigos_vehiculo
        WHERE vehiculo_id = ?
        LIMIT 1
    """, (
        vehiculo_id,
    ))
    codigo_existente = cursor.fetchone()

    if codigo_existente:
        conexion.close()
        flash(f"Este vehículo ya tiene un código asociado: {codigo_existente['codigo']}", "warning")
        return redirect(url_for("trabajador_panel") + "#trabajador-codigos")

    ahora = fecha_actual()

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
                flash(f"Código de canje generado: {codigo_generado}", "success")
                break

            except sqlite3.IntegrityError:
                conexion.rollback()
                codigo_generado = None

        if not codigo_generado:
            flash("No se pudo generar un código único. Intenta nuevamente.", "error")

    except Exception as error:
        conexion.rollback()
        print("Error al generar código desde panel trabajador:", error)
        flash("No se pudo generar el código de canje.", "error")

    finally:
        conexion.close()

    return redirect(url_for("trabajador_panel") + "#trabajador-codigos")


@app.route("/trabajador/vehiculos/<int:vehiculo_id>/archivar", methods=["POST"])
@login_required
@personal_required
def trabajador_archivar_vehiculo(vehiculo_id):

    asegurar_migraciones_admin()

    motivo = request.form.get("motivo_archivado", "").strip()
    ahora = fecha_actual()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT
                *,
                COALESCE(archivado, 0) AS archivado_normalizado
            FROM vehiculos
            WHERE id = ?
        """, (
            vehiculo_id,
        ))

        vehiculo = cursor.fetchone()

        if not vehiculo:
            flash("Vehículo no encontrado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        if vehiculo["archivado_normalizado"] == 1:
            flash("Este vehículo ya estaba archivado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        cursor.execute("""
            UPDATE vehiculos
            SET
                archivado = 1,
                archivado_en = ?,
                archivado_por = ?,
                motivo_archivado = ?,
                activo = 0,
                actualizado_en = ?
            WHERE id = ?
        """, (
            ahora,
            session["usuario_id"],
            motivo or "Archivado desde panel trabajador",
            ahora,
            vehiculo_id
        ))

        conexion.commit()
        flash("Vehículo archivado correctamente. Administración podrá verlo en Archivados.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al archivar vehículo desde panel trabajador:", error)
        flash("No se pudo archivar el vehículo.", "error")

    finally:
        conexion.close()

    return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")


@app.route("/trabajador/codigos/<int:codigo_id>/reactivar", methods=["POST"])
@login_required
@personal_required
def trabajador_reactivar_codigo_vehiculo(codigo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        codigo, error = reactivar_codigo_vehiculo_seguro(cursor, codigo_id)

        if error:
            conexion.rollback()
            flash(error, "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-codigos")

        conexion.commit()
        flash(f"Código reactivado correctamente: {codigo['codigo']}", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al reactivar código desde panel trabajador:", error)
        flash("No se pudo reactivar el código.", "error")

    finally:
        conexion.close()

    return redirect(url_for("trabajador_panel") + "#trabajador-codigos")


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

    segundos_restantes = segundos_bloqueo_login(correo)

    if segundos_restantes > 0:
        minutos = max(1, segundos_restantes // 60)
        flash(f"Demasiados intentos fallidos. Intenta nuevamente en {minutos} minuto(s).", "warning")
        return redirect("/login")

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,)
    )

    usuario = cursor.fetchone()
    conexion.close()

    if not usuario:
        registrar_login_fallido(correo)
        flash("Correo o contraseña incorrectos.", "error")
        return redirect("/login")

    if not check_password_hash(usuario["password"], password):
        registrar_login_fallido(correo)
        flash("Correo o contraseña incorrectos.", "error")
        return redirect("/login")

    if usuario.keys() and "activo" in usuario.keys() and usuario["activo"] == 0:
        registrar_login_fallido(correo)
        flash("Esta cuenta está desactivada. Contacta con administración.", "warning")
        return redirect("/login")

    limpiar_login_fallido(correo)

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

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,)
    )

    if cursor.fetchone():
        conexion.close()
        flash("Este correo ya está registrado.", "warning")
        return redirect("/login")

    password_hash = generate_password_hash(password)

    ahora = fecha_actual()

    cursor.execute("""
        INSERT INTO usuarios (
            nombre,
            correo,
            password,
            rol,
            activo,
            creado_en
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        nombre,
        correo,
        password_hash,
        "USUARIO",
        1,
        ahora
    ))

    conexion.commit()
    conexion.close()

    flash("Cuenta creada correctamente.", "success")

    return redirect("/login")


# ================= PERFIL =================

@app.route("/perfil")
@login_required
def perfil():

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            usuarios_vehiculos.id AS usuario_vehiculo_id,
            usuarios_vehiculos.usuario_id,
            usuarios_vehiculos.vehiculo_id,
            usuarios_vehiculos.codigo_vehiculo_id,
            usuarios_vehiculos.kilometraje_inicial,
            usuarios_vehiculos.fecha_registro,
            vehiculos.id AS id,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            vehiculos.tipo_vehiculo,
            vehiculos.combustible,
            vehiculos.transmision,
            vehiculos.kilometraje AS kilometraje_catalogo,
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

    filas_vehiculos = cursor.fetchall()
    conexion.close()

    mis_vehiculos = []

    for fila in filas_vehiculos:
        vehiculo = dict(fila)

        kilometraje_inicial = normalizar_kilometraje(
            vehiculo.get("kilometraje_inicial")
        )

        kilometraje_catalogo = normalizar_kilometraje(
            vehiculo.get("kilometraje_catalogo")
        )

        vehiculo["kilometraje_inicial"] = kilometraje_inicial
        vehiculo["kilometraje_catalogo"] = kilometraje_catalogo

        # profile.html usa vehiculo.kilometraje para mostrar
        # "Kilometraje inicial". Por eso priorizamos el kilometraje guardado
        # en usuarios_vehiculos al momento del canje.
        vehiculo["kilometraje"] = (
            kilometraje_inicial
            if kilometraje_inicial is not None
            else kilometraje_catalogo
        )

        vehiculo["imagen"] = obtener_nombre_imagen_vehiculo(
            vehiculo.get("imagen")
        )

        mis_vehiculos.append(vehiculo)

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
        flash("Ingresa el código de activación del vehículo.", "warning")
        return redirect("/perfil")

    asegurar_migraciones_admin()

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
                vehiculos.activo AS vehiculo_activo,
                COALESCE(vehiculos.archivado, 0) AS vehiculo_archivado
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
            flash("Código inválido. Verifica el código entregado por la concesionaria.", "error")
            return redirect("/perfil")

        if codigo["activo"] != 1:
            conexion.rollback()
            flash("Este código está inactivo. Contacta con la concesionaria.", "warning")
            return redirect("/perfil")

        if codigo["usado"] == 1:
            conexion.rollback()
            flash("Este código ya fue utilizado.", "warning")
            return redirect("/perfil")

        if (
            codigo["vehiculo_activo"] != 1
            or codigo["estado_vehiculo"] == "Vendido"
            or codigo["vehiculo_archivado"] == 1
        ):
            conexion.rollback()
            flash("Este vehículo ya no está disponible para registro.", "warning")
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
            flash("Este vehículo ya fue registrado por otro usuario.", "warning")
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
            normalizar_kilometraje(codigo["kilometraje"]) or 0,
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
            f"{codigo['marca']} {codigo['modelo']} {codigo['anio']}.",
            "success"
        )

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Este vehículo ya fue registrado anteriormente.", "warning")

    except Exception as error:
        conexion.rollback()
        print("Error al canjear código de vehículo:", error)
        flash("No se pudo registrar el vehículo. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect("/perfil")


# ================= FOTO DE PERFIL =================

@app.route("/perfil/foto", methods=["POST"])
@login_required
def actualizar_foto_perfil():

    if "foto_perfil" not in request.files:
        flash("No seleccionaste ninguna imagen.", "warning")
        return redirect("/perfil")

    archivo = request.files["foto_perfil"]

    if archivo.filename == "":
        flash("No seleccionaste ninguna imagen.", "warning")
        return redirect("/perfil")

    extensiones_permitidas = {"jpg", "jpeg", "png", "webp"}

    extension = archivo.filename.rsplit(".", 1)[-1].lower()

    if extension not in extensiones_permitidas:
        flash("Formato no permitido. Usa JPG, PNG o WEBP.", "warning")
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
        flash("No se pudo subir la imagen. Intenta nuevamente.", "error")
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

    flash("Foto de perfil actualizada correctamente.", "success")
    return redirect("/perfil")


# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ================= CATALOG =================
# Catálogo público conectado a datos reales

CATALOG_ESTADO_NORMALIZADO_SQL = "COALESCE(NULLIF(TRIM(estado), ''), 'Disponible')"
CATALOG_BASE_WHERE_SQL = f"""
    activo = 1
    AND COALESCE(archivado, 0) = 0
    AND {CATALOG_ESTADO_NORMALIZADO_SQL} IN ('Disponible', 'Reservado')
"""
CATALOG_PER_PAGE_PERMITIDOS = {8, 12, 16, 24}
CATALOG_ORDENES_SQL = {
    "recientes": "id DESC",
    "precio_asc": "COALESCE(precio, 0) ASC, id DESC",
    "precio_desc": "COALESCE(precio, 0) DESC, id DESC",
    "anio_desc": "COALESCE(anio, 0) DESC, id DESC",
    "km_asc": "COALESCE(kilometraje, 0) ASC, id DESC",
    "marca_asc": "LOWER(COALESCE(marca, '')) ASC, LOWER(COALESCE(modelo, '')) ASC, id DESC",
}


def limpiar_texto_catalogo(valor, maximo=80):
    texto = str(valor or "").strip()
    texto = re.sub(r"[\x00-\x1f\x7f]+", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto[:maximo]


def escapar_like_sql(valor):
    return (
        str(valor or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def obtener_lista_filtro_catalogo(nombre, limite=30, maximo_texto=60):
    valores = []

    for valor in request.args.getlist(nombre):
        partes = str(valor or "").split(",")

        for parte in partes:
            texto = limpiar_texto_catalogo(parte, maximo_texto)

            if not texto:
                continue

            if texto not in valores:
                valores.append(texto)

            if len(valores) >= limite:
                return valores

    return valores


def obtener_entero_filtro_catalogo(nombre, predeterminado=None, minimo=None, maximo=None):
    valor = request.args.get(nombre)

    if valor is None or str(valor).strip() == "":
        return predeterminado

    try:
        numero = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        return predeterminado

    if minimo is not None:
        numero = max(minimo, numero)

    if maximo is not None:
        numero = min(maximo, numero)

    return numero


def obtener_precio_filtro_catalogo(nombre, predeterminado=None, minimo=None, maximo=None):
    valor = request.args.get(nombre)

    if valor is None or str(valor).strip() == "":
        return predeterminado

    numero = normalizar_precio(valor)

    if numero is None:
        return predeterminado

    if minimo is not None:
        numero = max(float(minimo), numero)

    if maximo is not None:
        numero = min(float(maximo), numero)

    return numero


def construir_paginas_catalogo(pagina_actual, total_paginas):
    if total_paginas <= 1:
        return [1]

    if total_paginas <= 7:
        return list(range(1, total_paginas + 1))

    paginas = [1]
    inicio = max(2, pagina_actual - 1)
    fin = min(total_paginas - 1, pagina_actual + 1)

    if inicio > 2:
        paginas.append("...")

    for pagina in range(inicio, fin + 1):
        paginas.append(pagina)

    if fin < total_paginas - 1:
        paginas.append("...")

    paginas.append(total_paginas)
    return paginas


def obtener_opciones_catalogo(cursor, columna, alias_estado=False):
    if alias_estado:
        expresion = CATALOG_ESTADO_NORMALIZADO_SQL
    else:
        expresion = f"TRIM(COALESCE({columna}, ''))"

    cursor.execute(f"""
        SELECT
            {expresion} AS valor,
            COUNT(*) AS total
        FROM vehiculos
        WHERE {CATALOG_BASE_WHERE_SQL}
          AND {expresion} IS NOT NULL
          AND TRIM({expresion}) != ''
        GROUP BY {expresion}
        ORDER BY LOWER({expresion}) ASC
    """)

    return [
        {
            "valor": fila["valor"],
            "total": fila["total"]
        }
        for fila in cursor.fetchall()
        if fila["valor"]
    ]


def obtener_total_catalogo(cursor, condicion_extra="", parametros=()):
    sql = f"""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE {CATALOG_BASE_WHERE_SQL}
    """

    if condicion_extra:
        sql += f" AND {condicion_extra}"

    cursor.execute(sql, tuple(parametros))
    return cursor.fetchone()[0]


@app.route("/catalog")
def catalog():

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute(f"""
            SELECT
                COALESCE(MIN(precio), 0) AS precio_min,
                COALESCE(MAX(precio), 0) AS precio_max,
                COALESCE(MIN(anio), 1980) AS anio_min,
                COALESCE(MAX(anio), 2035) AS anio_max,
                COALESCE(MIN(kilometraje), 0) AS kilometraje_min,
                COALESCE(MAX(kilometraje), 0) AS kilometraje_max
            FROM vehiculos
            WHERE {CATALOG_BASE_WHERE_SQL}
        """)
        limites = cursor.fetchone()

        precio_min_catalogo = int(limites["precio_min"] or 0)
        precio_max_catalogo = int(limites["precio_max"] or 0)
        anio_min_catalogo = int(limites["anio_min"] or 1980)
        anio_max_catalogo = int(limites["anio_max"] or 2035)
        kilometraje_min_catalogo = int(limites["kilometraje_min"] or 0)
        kilometraje_max_catalogo = int(limites["kilometraje_max"] or 0)

        # Evita sliders con mínimo y máximo idénticos cuando hay una sola unidad.
        if precio_max_catalogo <= precio_min_catalogo:
            precio_max_catalogo = precio_min_catalogo + 1000

        if anio_max_catalogo <= anio_min_catalogo:
            anio_max_catalogo = anio_min_catalogo + 1

        if kilometraje_max_catalogo <= kilometraje_min_catalogo:
            kilometraje_max_catalogo = kilometraje_min_catalogo + 1000

        q = limpiar_texto_catalogo(request.args.get("q", ""), 80)
        marcas = obtener_lista_filtro_catalogo("marca")
        tipos = obtener_lista_filtro_catalogo("tipo")
        combustibles = obtener_lista_filtro_catalogo("combustible")
        transmisiones = obtener_lista_filtro_catalogo("transmision")
        estados = obtener_lista_filtro_catalogo("estado")

        precio_min = obtener_precio_filtro_catalogo(
            "precio_min",
            precio_min_catalogo,
            precio_min_catalogo,
            precio_max_catalogo
        )
        precio_max = obtener_precio_filtro_catalogo(
            "precio_max",
            precio_max_catalogo,
            precio_min_catalogo,
            precio_max_catalogo
        )

        if precio_min > precio_max:
            precio_min, precio_max = precio_max, precio_min

        anio_min = obtener_entero_filtro_catalogo(
            "anio_min",
            anio_min_catalogo,
            anio_min_catalogo,
            anio_max_catalogo
        )
        anio_max = obtener_entero_filtro_catalogo(
            "anio_max",
            anio_max_catalogo,
            anio_min_catalogo,
            anio_max_catalogo
        )

        if anio_min > anio_max:
            anio_min, anio_max = anio_max, anio_min

        kilometraje_min = obtener_entero_filtro_catalogo(
            "kilometraje_min",
            kilometraje_min_catalogo,
            kilometraje_min_catalogo,
            kilometraje_max_catalogo
        )
        kilometraje_max = obtener_entero_filtro_catalogo(
            "kilometraje_max",
            kilometraje_max_catalogo,
            kilometraje_min_catalogo,
            kilometraje_max_catalogo
        )

        if kilometraje_min > kilometraje_max:
            kilometraje_min, kilometraje_max = kilometraje_max, kilometraje_min

        ordenar = limpiar_texto_catalogo(request.args.get("ordenar", "recientes"), 30)

        if ordenar not in CATALOG_ORDENES_SQL:
            ordenar = "recientes"

        per_page = obtener_entero_filtro_catalogo("per_page", 8, 1, 100)

        if per_page not in CATALOG_PER_PAGE_PERMITIDOS:
            per_page = 8

        pagina_actual = obtener_entero_filtro_catalogo("page", 1, 1, 10_000)

        filtros_where = [CATALOG_BASE_WHERE_SQL]
        parametros = []

        if q:
            like_q = f"%{escapar_like_sql(q.lower())}%"
            filtros_where.append(f"""
                (
                    LOWER(COALESCE(marca, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(modelo, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(codigo_catalogo, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(tipo_vehiculo, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(combustible, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(transmision, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(descripcion, '')) LIKE ? ESCAPE '\\'
                    OR CAST(COALESCE(anio, '') AS TEXT) LIKE ? ESCAPE '\\'
                )
            """)
            parametros.extend([like_q] * 8)

        filtros_in = [
            ("marca", marcas, "LOWER(TRIM(COALESCE(marca, '')))", False),
            ("tipo", tipos, "LOWER(TRIM(COALESCE(tipo_vehiculo, '')))", False),
            ("combustible", combustibles, "LOWER(TRIM(COALESCE(combustible, '')))", False),
            ("transmision", transmisiones, "LOWER(TRIM(COALESCE(transmision, '')))", False),
            ("estado", estados, f"LOWER({CATALOG_ESTADO_NORMALIZADO_SQL})", True),
        ]

        for _, valores, expresion, _ in filtros_in:
            if not valores:
                continue

            placeholders = ", ".join("?" for _ in valores)
            filtros_where.append(f"{expresion} IN ({placeholders})")
            parametros.extend(valor.lower() for valor in valores)

        filtros_where.append("COALESCE(precio, 0) BETWEEN ? AND ?")
        parametros.extend([precio_min, precio_max])

        filtros_where.append("COALESCE(anio, 0) BETWEEN ? AND ?")
        parametros.extend([anio_min, anio_max])

        filtros_where.append("COALESCE(kilometraje, 0) BETWEEN ? AND ?")
        parametros.extend([kilometraje_min, kilometraje_max])

        where_sql = " AND ".join(f"({condicion})" for condicion in filtros_where)

        cursor.execute(f"""
            SELECT COUNT(*)
            FROM vehiculos
            WHERE {where_sql}
        """, parametros)
        total_filtrados = cursor.fetchone()[0]

        total_paginas = max(1, (total_filtrados + per_page - 1) // per_page)
        pagina_actual = min(max(1, pagina_actual), total_paginas)
        offset = (pagina_actual - 1) * per_page

        cursor.execute(f"""
            SELECT *
            FROM vehiculos
            WHERE {where_sql}
            ORDER BY {CATALOG_ORDENES_SQL[ordenar]}
            LIMIT ? OFFSET ?
        """, parametros + [per_page, offset])
        vehiculos = cursor.fetchall()

        marcas_catalogo = obtener_opciones_catalogo(cursor, "marca")
        tipos_catalogo = obtener_opciones_catalogo(cursor, "tipo_vehiculo")
        combustibles_catalogo = obtener_opciones_catalogo(cursor, "combustible")
        transmisiones_catalogo = obtener_opciones_catalogo(cursor, "transmision")
        estados_catalogo = obtener_opciones_catalogo(cursor, "estado", alias_estado=True)

        total_vehiculos = obtener_total_catalogo(cursor)
        total_suv = obtener_total_catalogo(cursor, "LOWER(TRIM(COALESCE(tipo_vehiculo, ''))) = ?", ("suv",))
        total_camionetas = obtener_total_catalogo(
            cursor,
            "LOWER(TRIM(COALESCE(tipo_vehiculo, ''))) IN (?, ?)",
            ("camioneta", "pickup")
        )
        total_hibridos = obtener_total_catalogo(
            cursor,
            "LOWER(TRIM(COALESCE(combustible, ''))) IN (?, ?)",
            ("híbrido", "eléctrico")
        )
        total_disponibles = obtener_total_catalogo(
            cursor,
            f"{CATALOG_ESTADO_NORMALIZADO_SQL} = ?",
            ("Disponible",)
        )

        rango_inicio = 0 if total_filtrados == 0 else offset + 1
        rango_fin = min(offset + per_page, total_filtrados)

        filtros = {
            "q": q,
            "marcas": marcas,
            "tipos": tipos,
            "combustibles": combustibles,
            "transmisiones": transmisiones,
            "estados": estados,
            "precio_min": precio_min,
            "precio_max": precio_max,
            "anio_min": anio_min,
            "anio_max": anio_max,
            "kilometraje_min": kilometraje_min,
            "kilometraje_max": kilometraje_max,
            "ordenar": ordenar,
            "per_page": per_page,
        }

    finally:
        conexion.close()

    return render_template(
        "catalog.html",
        vehiculos=vehiculos,
        marcas_catalogo=marcas_catalogo,
        tipos_catalogo=tipos_catalogo,
        combustibles_catalogo=combustibles_catalogo,
        transmisiones_catalogo=transmisiones_catalogo,
        estados_catalogo=estados_catalogo,
        precio_min_catalogo=precio_min_catalogo,
        precio_max_catalogo=precio_max_catalogo,
        anio_min_catalogo=anio_min_catalogo,
        anio_max_catalogo=anio_max_catalogo,
        kilometraje_min_catalogo=kilometraje_min_catalogo,
        kilometraje_max_catalogo=kilometraje_max_catalogo,
        filtros=filtros,
        total_vehiculos=total_vehiculos,
        total_suv=total_suv,
        total_camionetas=total_camionetas,
        total_hibridos=total_hibridos,
        total_disponibles=total_disponibles,
        total_filtrados=total_filtrados,
        pagina_actual=pagina_actual,
        total_paginas=total_paginas,
        paginas_catalogo=construir_paginas_catalogo(pagina_actual, total_paginas),
        rango_inicio=rango_inicio,
        rango_fin=rango_fin,
        trabajador_panel_url=url_for("trabajador_panel") if str(session.get("rol", "")).upper() in {"ADMIN", "TRABAJADOR"} else ""
    )


# ================= ADMIN =================

@app.route("/admin")
@login_required
@admin_required
def admin_inicio():
    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos")
@login_required
@admin_required
def admin_vehiculos():

    asegurar_migraciones_admin()

    editar_id = request.args.get("editar", type=int)

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 0
        ORDER BY id DESC
    """)

    vehiculos = cursor.fetchall()

    vehiculo_editar = None

    if editar_id:
        cursor.execute("""
            SELECT *
            FROM vehiculos
            WHERE id = ?
              AND COALESCE(archivado, 0) = 0
        """, (
            editar_id,
        ))
        vehiculo_editar = cursor.fetchone()

        if not vehiculo_editar:
            flash("El vehículo no existe o fue archivado.", "warning")
            conexion.close()
            return redirigir_admin("vehiculos")

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

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 0
    """)
    total_vehiculos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 1
          AND COALESCE(archivado, 0) = 0
    """)
    vehiculos_activos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE activo = 0
          AND COALESCE(archivado, 0) = 0
    """)
    vehiculos_inactivos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vehiculos
        WHERE COALESCE(archivado, 0) = 1
    """)
    vehiculos_archivados_total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            vehiculos.*,
            usuarios.nombre AS archivado_por_nombre
        FROM vehiculos
        LEFT JOIN usuarios
            ON usuarios.id = vehiculos.archivado_por
        WHERE COALESCE(vehiculos.archivado, 0) = 1
        ORDER BY vehiculos.archivado_en DESC, vehiculos.id DESC
    """)
    vehiculos_archivados = cursor.fetchall()

    cursor.execute("""
        SELECT
            usuarios_vehiculos.id,
            usuarios_vehiculos.fecha_registro,
            usuarios_vehiculos.kilometraje_inicial,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            codigos_vehiculo.codigo AS codigo_canje
        FROM usuarios_vehiculos
        INNER JOIN usuarios
            ON usuarios.id = usuarios_vehiculos.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = usuarios_vehiculos.vehiculo_id
        LEFT JOIN codigos_vehiculo
            ON codigos_vehiculo.id = usuarios_vehiculos.codigo_vehiculo_id
        ORDER BY usuarios_vehiculos.id DESC
    """)
    ventas_canje = cursor.fetchall()

    cursor.execute("""
        SELECT
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.rol,
            usuarios.foto_perfil,
            COALESCE(usuarios.activo, 1) AS activo,
            usuarios.creado_en,
            usuarios.actualizado_en,
            COUNT(usuarios_vehiculos.id) AS total_vehiculos
        FROM usuarios
        LEFT JOIN usuarios_vehiculos
            ON usuarios_vehiculos.usuario_id = usuarios.id
        GROUP BY usuarios.id
        ORDER BY usuarios.id DESC
    """)
    usuarios_admin = cursor.fetchall()

    cursor.execute("""
        SELECT
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.rol AS cargo,
            usuarios.foto_perfil,
            COALESCE(usuarios.activo, 1) AS activo,
            usuarios.creado_en,
            usuarios.actualizado_en
        FROM usuarios
        WHERE usuarios.rol != 'USUARIO'
        ORDER BY usuarios.id DESC
    """)
    trabajadores_admin = cursor.fetchall()

    cursor.execute("""
        SELECT
            canjes_reversados.*,
            usuarios.nombre AS reversado_por_nombre
        FROM canjes_reversados
        LEFT JOIN usuarios
            ON usuarios.id = canjes_reversados.reversado_por
        ORDER BY canjes_reversados.id DESC
    """)
    canjes_reversados = cursor.fetchall()

    total_usuarios = len(usuarios_admin)
    total_trabajadores = len(trabajadores_admin)

    conexion.close()

    return render_template(
        "admin.html",
        vehiculos=vehiculos,
        vehiculo_editar=vehiculo_editar,
        total_vehiculos=total_vehiculos,
        vehiculos_activos=vehiculos_activos,
        vehiculos_inactivos=vehiculos_inactivos,
        vehiculos_archivados_total=vehiculos_archivados_total,
        vehiculos_archivados=vehiculos_archivados,
        ventas_canje=ventas_canje,
        usuarios_admin=usuarios_admin,
        trabajadores_admin=trabajadores_admin,
        canjes_reversados=canjes_reversados,
        total_usuarios=total_usuarios,
        total_trabajadores=total_trabajadores,
        codigos_por_vehiculo=codigos_por_vehiculo
    )


@app.route("/admin/vehiculos/guardar", methods=["POST"])
@login_required
@admin_required
def admin_guardar_vehiculo():

    asegurar_migraciones_admin()

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

    estados_permitidos = {
        "Disponible",
        "Reservado",
        "No disponible",
        "Vendido"
    }

    if estado not in estados_permitidos:
        estado = "Disponible"

    activo = 1 if request.form.get("activo") == "on" else 0

    # Si el admin marca manualmente un vehículo como vendido, debe quedar oculto.
    # Si luego fue un error y NO existe canje real, podrá cambiarse de vuelta
    # a Disponible y activarse normalmente.
    if estado == "Vendido":
        activo = 0

    if not codigo_catalogo or not marca or not modelo or not anio:
        flash("Código, marca, modelo y año son obligatorios.", "warning")
        return redirigir_admin("vehiculos")

    try:
        anio = int(anio)
        kilometraje = normalizar_kilometraje(kilometraje)
        precio = normalizar_precio(precio)
    except ValueError:
        flash("Año, kilometraje y precio deben ser valores numéricos.", "warning")
        return redirigir_admin("vehiculos")

    if kilometraje is None:
        flash("El kilometraje debe ser un valor numérico válido.", "warning")
        return redirigir_admin("vehiculos")

    if precio is None:
        flash("El precio debe ser un valor numérico válido.", "warning")
        return redirigir_admin("vehiculos")

    archivo_imagen = request.files.get("imagen")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()

        vehiculo_actual = None
        vehiculo_tiene_codigo = False
        vehiculo_tiene_registro_usuario = False

        if vehiculo_id:
            vehiculo_id = int(vehiculo_id)

            cursor.execute("""
                SELECT *
                FROM vehiculos
                WHERE id = ?
                  AND COALESCE(archivado, 0) = 0
            """, (
                vehiculo_id,
            ))

            vehiculo_actual = cursor.fetchone()

            if not vehiculo_actual:
                flash("El vehículo no existe o fue archivado.", "warning")
                return redirigir_admin("vehiculos")

            cursor.execute("""
                SELECT COUNT(*)
                FROM codigos_vehiculo
                WHERE vehiculo_id = ?
            """, (
                vehiculo_id,
            ))
            vehiculo_tiene_codigo = cursor.fetchone()[0] > 0

            cursor.execute("""
                SELECT COUNT(*)
                FROM usuarios_vehiculos
                WHERE vehiculo_id = ?
            """, (
                vehiculo_id,
            ))
            vehiculo_tiene_registro_usuario = cursor.fetchone()[0] > 0

            # Si existe en usuarios_vehiculos, el vehículo fue registrado por un
            # usuario. En ese caso no se puede "desvender" desde edición normal,
            # porque quedaría disponible en catálogo pero seguiría en el perfil.
            # Debe usarse la ruta de reversa de canje.
            if vehiculo_tiene_registro_usuario:
                if estado != "Vendido" or activo == 1:
                    flash("Este vehículo fue vendido por canje. Para corregirlo usa la reversa/anulación del canje.", "warning")
                    return redirigir_admin("ventas")

                estado = "Vendido"
                activo = 0

            referencia_bloqueada = (
                vehiculo_tiene_codigo
                or vehiculo_tiene_registro_usuario
            )

            if referencia_bloqueada and codigo_catalogo != vehiculo_actual["codigo_catalogo"]:
                flash("No puedes cambiar el código de catálogo de un vehículo que ya tiene código, venta o registro.", "warning")
                return redirigir_admin("vehiculos")

        try:
            imagen_guardada = guardar_imagen_vehiculo(archivo_imagen, codigo_catalogo)
        except ValueError as error:
            flash(str(error), "warning")
            return redirigir_admin("vehiculos")

        if vehiculo_id:

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

            flash("Vehículo actualizado correctamente.", "success")

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
                    creado_en,
                    archivado
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ahora,
                0
            ))

            flash("Vehículo creado correctamente.", "success")

        conexion.commit()

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe un vehículo con ese código de catálogo.", "warning")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar vehículo:", error)
        flash("No se pudo guardar el vehículo. Revisa los datos e intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/estado", methods=["POST"])
@login_required
@admin_required
def admin_cambiar_estado_vehiculo(vehiculo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            activo,
            estado,
            COALESCE(archivado, 0) AS archivado
        FROM vehiculos
        WHERE id = ?
    """, (
        vehiculo_id,
    ))

    vehiculo = cursor.fetchone()

    if not vehiculo:
        conexion.close()
        flash("Vehículo no encontrado.", "warning")
        return redirigir_admin("vehiculos")

    if vehiculo["archivado"] == 1:
        conexion.close()
        flash("No puedes cambiar la visibilidad de un vehículo archivado.", "warning")
        return redirigir_admin("vehiculos")

    if vehiculo["estado"] == "Vendido":
        if tiene_canje_real(cursor, vehiculo_id):
            conexion.close()
            flash("Este vehículo fue vendido por canje. Para reactivarlo primero debes reversar/anular el canje.", "warning")
            return redirigir_admin("ventas")

        # Vendido manualmente por error: se permite corregir desde el botón normal.
        cursor.execute("""
            UPDATE vehiculos
            SET
                activo = 1,
                estado = 'Disponible',
                actualizado_en = ?
            WHERE id = ?
        """, (
            fecha_actual(),
            vehiculo_id
        ))

        conexion.commit()
        conexion.close()

        flash("Venta manual corregida. El vehículo volvió a Disponible y visible en catálogo.", "success")
        return redirigir_admin("vehiculos")

    nuevo_estado = 0 if vehiculo["activo"] == 1 else 1

    cursor.execute("""
        UPDATE vehiculos
        SET activo = ?, actualizado_en = ?
        WHERE id = ?
    """, (
        nuevo_estado,
        fecha_actual(),
        vehiculo_id
    ))

    conexion.commit()
    conexion.close()

    if nuevo_estado == 1:
        flash("Vehículo activado en el catálogo.", "success")
    else:
        flash("Vehículo ocultado del catálogo.", "success")

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/codigo/generar", methods=["POST"])
@login_required
@admin_required
def admin_generar_codigo_vehiculo(vehiculo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            *,
            COALESCE(archivado, 0) AS archivado_normalizado
        FROM vehiculos
        WHERE id = ?
    """, (
        vehiculo_id,
    ))

    vehiculo = cursor.fetchone()

    if not vehiculo:
        conexion.close()
        flash("Vehículo no encontrado.", "warning")
        return redirigir_admin("vehiculos")

    if vehiculo["archivado_normalizado"] == 1:
        conexion.close()
        flash("No puedes generar código para un vehículo archivado.", "warning")
        return redirigir_admin("vehiculos")

    if vehiculo["estado"] == "Vendido":
        conexion.close()
        flash("No puedes generar código para un vehículo vendido.", "warning")
        return redirigir_admin("vehiculos")

    if vehiculo["activo"] != 1:
        conexion.close()
        flash("El vehículo debe estar activo en catálogo para generar un código.", "warning")
        return redirigir_admin("vehiculos")

    # Regla de negocio:
    # 1 vehículo real = máximo 1 código VNV, sin importar si está usado,
    # activo o inactivo.
    cursor.execute("""
        SELECT *
        FROM codigos_vehiculo
        WHERE vehiculo_id = ?
        LIMIT 1
    """, (
        vehiculo_id,
    ))

    codigo_existente = cursor.fetchone()

    if codigo_existente:
        conexion.close()

        if codigo_existente["usado"] == 1:
            flash(f"Este vehículo ya tuvo un código usado: {codigo_existente['codigo']}", "warning")
        elif codigo_existente["activo"] == 0:
            flash(f"Este vehículo ya tiene un código inactivo: {codigo_existente['codigo']}", "warning")
        else:
            flash(f"Este vehículo ya tiene un código generado: {codigo_existente['codigo']}", "warning")

        return redirigir_admin("vehiculos")

    ahora = fecha_actual()

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
                flash(f"Código de canje generado: {codigo_generado}", "success")
                break

            except sqlite3.IntegrityError:
                conexion.rollback()
                codigo_generado = None

        if not codigo_generado:
            flash("No se pudo generar un código único. Intenta nuevamente.", "error")

    except Exception as error:
        conexion.rollback()
        print("Error al generar código de canje:", error)
        flash("No se pudo generar el código de canje.", "error")

    finally:
        conexion.close()

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/archivar", methods=["POST"])
@login_required
@admin_required
def admin_archivar_vehiculo(vehiculo_id):

    asegurar_migraciones_admin()

    motivo = request.form.get("motivo_archivado", "").strip()
    ahora = fecha_actual()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT
                *,
                COALESCE(archivado, 0) AS archivado_normalizado
            FROM vehiculos
            WHERE id = ?
        """, (
            vehiculo_id,
        ))

        vehiculo = cursor.fetchone()

        if not vehiculo:
            flash("Vehículo no encontrado.", "warning")
            return redirigir_admin("vehiculos")

        if vehiculo["archivado_normalizado"] == 1:
            flash("Este vehículo ya estaba archivado.", "warning")
            return redirigir_admin("archivados")

        cursor.execute("""
            UPDATE vehiculos
            SET
                archivado = 1,
                archivado_en = ?,
                archivado_por = ?,
                motivo_archivado = ?,
                activo = 0,
                actualizado_en = ?
            WHERE id = ?
        """, (
            ahora,
            session["usuario_id"],
            motivo or "Archivado manualmente desde administración",
            ahora,
            vehiculo_id
        ))

        conexion.commit()
        flash("Vehículo archivado correctamente. Se conservará en el historial interno.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al archivar vehículo:", error)
        flash("No se pudo archivar el vehículo.", "error")

    finally:
        conexion.close()

    return redirigir_admin("archivados")


@app.route("/admin/canjes/<int:usuario_vehiculo_id>/reversar", methods=["POST"])
@login_required
@admin_required
def admin_reversar_canje(usuario_vehiculo_id):

    asegurar_migraciones_admin()

    motivo = request.form.get("motivo", "").strip()
    ahora = fecha_actual()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            SELECT
                usuarios_vehiculos.id AS usuario_vehiculo_id,
                usuarios_vehiculos.usuario_id,
                usuarios_vehiculos.vehiculo_id,
                usuarios_vehiculos.codigo_vehiculo_id,
                usuarios_vehiculos.kilometraje_inicial,
                usuarios_vehiculos.fecha_registro,
                usuarios.nombre AS usuario_nombre,
                usuarios.correo AS usuario_correo,
                vehiculos.codigo_catalogo,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio,
                COALESCE(vehiculos.archivado, 0) AS vehiculo_archivado,
                codigos_vehiculo.codigo AS codigo_canje
            FROM usuarios_vehiculos
            INNER JOIN usuarios
                ON usuarios.id = usuarios_vehiculos.usuario_id
            INNER JOIN vehiculos
                ON vehiculos.id = usuarios_vehiculos.vehiculo_id
            LEFT JOIN codigos_vehiculo
                ON codigos_vehiculo.id = usuarios_vehiculos.codigo_vehiculo_id
            WHERE usuarios_vehiculos.id = ?
            LIMIT 1
        """, (
            usuario_vehiculo_id,
        ))

        canje = cursor.fetchone()

        if not canje:
            conexion.rollback()
            flash("Registro de canje no encontrado.", "warning")
            return redirigir_admin("ventas")

        vehiculo_descripcion = (
            f"{canje['marca']} {canje['modelo']} {canje['anio']}"
        )

        cursor.execute("""
            INSERT INTO canjes_reversados (
                usuario_vehiculo_id,
                usuario_id,
                vehiculo_id,
                codigo_vehiculo_id,
                codigo_canje,
                usuario_nombre,
                usuario_correo,
                vehiculo_referencia,
                vehiculo_descripcion,
                kilometraje_inicial,
                fecha_registro_original,
                reversado_por,
                reversado_en,
                motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            canje["usuario_vehiculo_id"],
            canje["usuario_id"],
            canje["vehiculo_id"],
            canje["codigo_vehiculo_id"],
            canje["codigo_canje"],
            canje["usuario_nombre"],
            canje["usuario_correo"],
            canje["codigo_catalogo"],
            vehiculo_descripcion,
            canje["kilometraje_inicial"],
            canje["fecha_registro"],
            session["usuario_id"],
            ahora,
            motivo or "Reversa administrativa de canje"
        ))

        cursor.execute("""
            DELETE FROM usuarios_vehiculos
            WHERE id = ?
        """, (
            usuario_vehiculo_id,
        ))

        if canje["codigo_vehiculo_id"]:
            cursor.execute("""
                UPDATE codigos_vehiculo
                SET
                    usado = 0,
                    usado_por = NULL,
                    fecha_uso = NULL,
                    activo = 1
                WHERE id = ?
            """, (
                canje["codigo_vehiculo_id"],
            ))

        nuevo_activo = 0 if canje["vehiculo_archivado"] == 1 else 1

        cursor.execute("""
            UPDATE vehiculos
            SET
                estado = 'Disponible',
                activo = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (
            nuevo_activo,
            ahora,
            canje["vehiculo_id"]
        ))

        conexion.commit()

        if nuevo_activo == 1:
            flash("Canje reversado correctamente. El vehículo volvió a Disponible y visible en catálogo.", "success")
        else:
            flash("Canje reversado correctamente. El vehículo sigue oculto porque está archivado.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al reversar canje:", error)
        flash("No se pudo reversar el canje. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirigir_admin("ventas")


@app.route("/admin/codigos/<int:codigo_id>/desactivar", methods=["POST"])
@login_required
@admin_required
def admin_desactivar_codigo_vehiculo(codigo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM codigos_vehiculo WHERE id = ?",
        (codigo_id,)
    )

    codigo = cursor.fetchone()

    if not codigo:
        conexion.close()
        flash("Código no encontrado.", "warning")
        return redirigir_admin("vehiculos")

    if codigo["usado"] == 1:
        conexion.close()
        flash("No puedes desactivar un código que ya fue usado.", "warning")
        return redirigir_admin("vehiculos")

    cursor.execute("""
        UPDATE codigos_vehiculo
        SET activo = 0
        WHERE id = ?
    """, (
        codigo_id,
    ))

    conexion.commit()
    conexion.close()

    flash("Código de canje desactivado correctamente.", "success")
    return redirigir_admin("vehiculos")


@app.route("/admin/codigos/<int:codigo_id>/reactivar", methods=["POST"])
@login_required
@admin_required
def admin_reactivar_codigo_vehiculo(codigo_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        codigo, error = reactivar_codigo_vehiculo_seguro(cursor, codigo_id)

        if error:
            conexion.rollback()
            flash(error, "warning")
            return redirigir_admin("codigos")

        conexion.commit()
        flash(f"Código de canje reactivado correctamente: {codigo['codigo']}", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al reactivar código de canje:", error)
        flash("No se pudo reactivar el código de canje.", "error")

    finally:
        conexion.close()

    return redirigir_admin("codigos")


# ================= ADMIN USUARIOS / TRABAJADORES =================

@app.route("/admin/usuarios/crear", methods=["POST"])
@login_required
@admin_required
def admin_crear_usuario():

    asegurar_migraciones_admin()

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "").strip()
    rol = request.form.get("rol", "USUARIO").strip().upper()

    if rol == "ADMIN":
        flash("Los administradores solo pueden crearse desde consola raíz del proyecto.", "warning")
        return redirigir_admin("usuarios")

    if rol not in ROLES_CREABLES_DESDE_PANEL:
        flash("Rol no permitido desde el panel administrativo.", "warning")
        return redirigir_admin("usuarios")

    if not nombre or not correo or not password:
        flash("Nombre, correo y contraseña son obligatorios para crear la cuenta.", "warning")
        return redirigir_admin("usuarios")

    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "warning")
        return redirigir_admin("usuarios")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()
        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO usuarios (
                nombre,
                correo,
                password,
                rol,
                activo,
                creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            nombre,
            correo,
            password_hash,
            rol,
            1,
            ahora
        ))

        conexion.commit()

        if rol == "USUARIO":
            flash("Usuario creado correctamente.", "success")
            return redirigir_admin("usuarios")

        flash("Trabajador creado correctamente.", "success")
        return redirigir_admin("trabajadores")

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe una cuenta con ese correo.", "warning")

    except Exception as error:
        conexion.rollback()
        print("Error al crear usuario:", error)
        flash("No se pudo crear la cuenta. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirigir_admin("usuarios")


@app.route("/admin/usuarios/<int:usuario_id>/rol", methods=["POST"])
@login_required
@admin_required
def admin_actualizar_rol_usuario(usuario_id):

    asegurar_migraciones_admin()

    nuevo_rol = request.form.get("rol", "").strip().upper()

    if nuevo_rol == "ADMIN":
        flash("No puedes convertir usuarios en administradores desde el panel web.", "warning")
        return redirigir_admin("usuarios")

    if nuevo_rol not in ROLES_CREABLES_DESDE_PANEL:
        flash("Rol no permitido desde el panel administrativo.", "warning")
        return redirigir_admin("usuarios")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
        usuario = cursor.fetchone()

        if not usuario:
            flash("Usuario no encontrado.", "warning")
            return redirigir_admin("usuarios")

        if usuario["rol"] == "ADMIN":
            flash("Las cuentas administradoras solo se modifican desde consola raíz del proyecto.", "warning")
            return redirigir_admin("usuarios")

        cursor.execute("""
            UPDATE usuarios
            SET rol = ?, actualizado_en = ?
            WHERE id = ?
        """, (
            nuevo_rol,
            fecha_actual(),
            usuario_id
        ))

        conexion.commit()
        flash("Rol actualizado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar rol:", error)
        flash("No se pudo actualizar el rol del usuario.", "error")

    finally:
        conexion.close()

    return redirigir_admin("usuarios")


@app.route("/admin/usuarios/<int:usuario_id>/estado", methods=["POST"])
@login_required
@admin_required
def admin_cambiar_estado_usuario(usuario_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, rol, COALESCE(activo, 1) AS activo
            FROM usuarios
            WHERE id = ?
        """, (
            usuario_id,
        ))

        usuario = cursor.fetchone()

        if not usuario:
            flash("Usuario no encontrado.", "warning")
            return redirigir_admin("usuarios")

        if usuario_id == session.get("usuario_id"):
            flash("No puedes desactivar tu propia cuenta desde esta sesión.", "warning")
            return redirigir_admin("usuarios")

        if usuario["rol"] == "ADMIN":
            flash("Las cuentas administradoras solo se activan o desactivan desde consola raíz del proyecto.", "warning")
            return redirigir_admin("usuarios")

        nuevo_estado = 0 if usuario["activo"] == 1 else 1

        cursor.execute("""
            UPDATE usuarios
            SET activo = ?, actualizado_en = ?
            WHERE id = ?
        """, (
            nuevo_estado,
            fecha_actual(),
            usuario_id
        ))

        conexion.commit()

        if nuevo_estado == 1:
            flash("Cuenta activada correctamente.", "success")
        else:
            flash("Cuenta desactivada correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar estado de usuario:", error)
        flash("No se pudo actualizar el estado de la cuenta.", "error")

    finally:
        conexion.close()

    return redirigir_admin("usuarios")


# ================= ERROR PESO =================

@app.errorhandler(413)
def archivo_demasiado_grande(error):
    flash("La imagen es demasiado pesada. Intenta con una imagen más pequeña.", "warning")
    return redirect(request.referrer or "/perfil")


# ================= APP =================

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))

    app.run(host=host, port=port, debug=debug)