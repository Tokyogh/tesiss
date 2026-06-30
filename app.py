from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta, datetime
from calendar import monthrange
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



def normalizar_fecha(valor):
    """
    Valida fechas HTML tipo YYYY-MM-DD.
    Devuelve la fecha normalizada o None si está vacía/no válida.
    """

    texto = str(valor or "").strip()

    if not texto:
        return None

    try:
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def formatear_fecha_visible(valor):
    """
    Convierte YYYY-MM-DD a DD/MM/YYYY para mostrarlo en templates.
    Si no puede convertirlo, devuelve el valor original.
    """

    if not valor:
        return ""

    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def sumar_meses(fecha_base, meses):
    """
    Suma meses a una fecha manteniendo el día cuando sea posible.
    Si el mes destino tiene menos días, usa el último día válido.
    """

    if not fecha_base:
        return None

    try:
        fecha = datetime.strptime(str(fecha_base)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

    total_meses = (fecha.year * 12 + fecha.month - 1) + int(meses or 0)
    nuevo_anio = total_meses // 12
    nuevo_mes = total_meses % 12 + 1
    nuevo_dia = min(fecha.day, monthrange(nuevo_anio, nuevo_mes)[1])

    return datetime(nuevo_anio, nuevo_mes, nuevo_dia).strftime("%Y-%m-%d")


def normalizar_tipo_servicio(tipo_servicio):
    texto = str(tipo_servicio or "").strip().lower()
    texto = texto.replace("á", "a").replace("é", "e").replace("í", "i")
    texto = texto.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def reglas_mantenimiento(tipo_servicio):
    """
    Devuelve el intervalo sugerido según el tipo de servicio.
    La clave es flexible para aceptar textos escritos por el trabajador.
    """

    tipo = normalizar_tipo_servicio(tipo_servicio)

    if "aceite" in tipo:
        return 5000, 6

    if "revision general" in tipo or "general" in tipo:
        return 10000, 12

    if "freno" in tipo:
        return 15000, 12

    if "llanta" in tipo or "neumatic" in tipo:
        return 10000, 12

    if "bateria" in tipo:
        return 20000, 18

    return 10000, 12


def calcular_proximo_mantenimiento(tipo_servicio, kilometraje_actual, fecha_servicio):
    intervalo_km, intervalo_meses = reglas_mantenimiento(tipo_servicio)

    proximo_kilometraje = None

    if kilometraje_actual is not None:
        proximo_kilometraje = kilometraje_actual + intervalo_km

    proxima_fecha = sumar_meses(fecha_servicio, intervalo_meses)

    return {
        "intervalo_km": intervalo_km,
        "intervalo_meses": intervalo_meses,
        "proximo_kilometraje": proximo_kilometraje,
        "proxima_fecha": proxima_fecha
    }


def estado_programacion_mantenimiento(proxima_fecha, proximo_kilometraje, kilometraje_referencia=None):
    """Calcula el estado visible para el próximo servicio."""

    hoy = datetime.now().date()
    limite_proximo = hoy + timedelta(days=30)
    estado = "programado"
    estado_texto = "Programado"
    detalle = []

    if proxima_fecha:
        fecha_visible = formatear_fecha_visible(proxima_fecha)
        detalle.append(f"Fecha sugerida: {fecha_visible}")

        try:
            fecha_objetivo = datetime.strptime(str(proxima_fecha)[:10], "%Y-%m-%d").date()

            if fecha_objetivo <= hoy:
                estado = "vencido"
                estado_texto = "Vencido"
            elif fecha_objetivo <= limite_proximo and estado != "vencido":
                estado = "proximo"
                estado_texto = "Próximo"
        except ValueError:
            pass

    if proximo_kilometraje is not None:
        detalle.append(f"Kilometraje sugerido: {proximo_kilometraje:,} km".replace(",", "."))

        if kilometraje_referencia is not None:
            km_restante = proximo_kilometraje - kilometraje_referencia

            if km_restante <= 0:
                estado = "vencido"
                estado_texto = "Vencido"
            elif km_restante <= 1000 and estado != "vencido":
                estado = "proximo"
                estado_texto = "Próximo"

            detalle.append(f"Referencia actual: {kilometraje_referencia:,} km".replace(",", "."))

    return estado, estado_texto, " • ".join(detalle)


def obtener_establecimiento_usuario(cursor, usuario_id):
    if not usuario_id:
        return ""

    try:
        cursor.execute("""
            SELECT COALESCE(establecimiento, '') AS establecimiento
            FROM usuarios
            WHERE id = ?
        """, (
            usuario_id,
        ))

        fila = cursor.fetchone()

        if fila:
            return str(fila["establecimiento"] or "").strip()
    except Exception:
        return ""

    return ""

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
            "actualizado_en": "TEXT",
            "establecimiento": "TEXT"
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mantenimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            vehiculo_id INTEGER NOT NULL,
            usuario_vehiculo_id INTEGER,
            registrado_por INTEGER,
            tipo_servicio TEXT NOT NULL,
            descripcion TEXT,
            kilometraje_actual INTEGER,
            fecha_servicio TEXT NOT NULL,
            intervalo_km INTEGER,
            intervalo_meses INTEGER,
            proximo_kilometraje INTEGER,
            proxima_fecha TEXT,
            observaciones TEXT,
            establecimiento TEXT,
            estado TEXT DEFAULT 'Realizado',
            costo REAL DEFAULT 0,
            taller TEXT,
            kilometraje INTEGER,
            proximo_servicio_fecha TEXT,
            proximo_servicio_km INTEGER,
            creado_en TEXT,
            actualizado_en TEXT,
            anulado INTEGER DEFAULT 0,
            anulado_por INTEGER,
            anulado_en TEXT,
            motivo_anulacion TEXT
        )
    """)

    if tabla_existe(cursor, "mantenimientos"):
        columnas_mantenimientos = {
            "registrado_por": "INTEGER",
            "kilometraje_actual": "INTEGER",
            "intervalo_km": "INTEGER",
            "intervalo_meses": "INTEGER",
            "proximo_kilometraje": "INTEGER",
            "proxima_fecha": "TEXT",
            "observaciones": "TEXT",
            "establecimiento": "TEXT",
            "estado": "TEXT DEFAULT 'Realizado'",
            "anulado": "INTEGER DEFAULT 0",
            "anulado_por": "INTEGER",
            "anulado_en": "TEXT",
            "motivo_anulacion": "TEXT"
        }

        for columna, definicion in columnas_mantenimientos.items():
            agregar_columna_si_falta(cursor, "mantenimientos", columna, definicion)

        cursor.execute("""
            UPDATE mantenimientos
            SET
                kilometraje_actual = COALESCE(kilometraje_actual, kilometraje),
                proximo_kilometraje = COALESCE(proximo_kilometraje, proximo_servicio_km),
                proxima_fecha = COALESCE(proxima_fecha, proximo_servicio_fecha),
                establecimiento = COALESCE(establecimiento, taller),
                observaciones = COALESCE(observaciones, descripcion),
                estado = COALESCE(NULLIF(TRIM(estado), ''), 'Realizado'),
                anulado = COALESCE(anulado, 0)
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manuales_vehiculo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo_documento TEXT,
            archivo TEXT,
            enlace TEXT,
            descripcion TEXT,
            subido_por INTEGER,
            creado_en TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    if tabla_existe(cursor, "manuales_vehiculo"):
        columnas_manuales = {
            "tipo_documento": "TEXT",
            "archivo": "TEXT",
            "enlace": "TEXT",
            "descripcion": "TEXT",
            "subido_por": "INTEGER",
            "creado_en": "TEXT",
            "activo": "INTEGER DEFAULT 1"
        }

        for columna, definicion in columnas_manuales.items():
            agregar_columna_si_falta(cursor, "manuales_vehiculo", columna, definicion)

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_usuario_fecha
        ON mantenimientos(usuario_id, fecha_servicio)
        """,
        "índice de mantenimientos por usuario y fecha"
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_vehiculo
        ON mantenimientos(vehiculo_id)
        """,
        "índice de mantenimientos por vehículo"
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_anulado
        ON mantenimientos(anulado)
        """,
        "índice de mantenimientos anulados"
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_manuales_vehiculo
        ON manuales_vehiculo(vehiculo_id, activo)
        """,
        "índice de manuales por vehículo"
    )

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

    # La selección de cliente/vehículo para mantenimiento ahora se hace por búsqueda AJAX.
    # No cargamos todos los registros aquí para evitar listas enormes cuando haya miles de clientes.
    vehiculos_clientes = []

    cursor.execute("""
        SELECT
            mantenimientos.*,
            COALESCE(mantenimientos.kilometraje_actual, mantenimientos.kilometraje) AS km_servicio,
            COALESCE(mantenimientos.proximo_kilometraje, mantenimientos.proximo_servicio_km) AS km_proximo,
            COALESCE(mantenimientos.proxima_fecha, mantenimientos.proximo_servicio_fecha) AS fecha_proxima,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            registrador.nombre AS registrado_por_nombre,
            registrador.rol AS registrado_por_rol,
            registrador.establecimiento AS registrado_por_establecimiento
        FROM mantenimientos
        INNER JOIN usuarios
            ON usuarios.id = mantenimientos.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = mantenimientos.vehiculo_id
        LEFT JOIN usuarios AS registrador
            ON registrador.id = mantenimientos.registrado_por
        WHERE COALESCE(mantenimientos.anulado, 0) = 0
        ORDER BY DATE(mantenimientos.fecha_servicio) DESC, mantenimientos.id DESC
        LIMIT 80
    """)
    mantenimientos = []

    for fila in cursor.fetchall():
        mantenimiento = dict(fila)
        mantenimiento["fecha_visible"] = formatear_fecha_visible(mantenimiento.get("fecha_servicio"))
        mantenimiento["proxima_fecha"] = mantenimiento.get("fecha_proxima")
        mantenimiento["proxima_fecha_visible"] = formatear_fecha_visible(mantenimiento.get("fecha_proxima"))
        mantenimiento["kilometraje_actual"] = normalizar_kilometraje(mantenimiento.get("km_servicio"))
        mantenimiento["proximo_kilometraje"] = normalizar_kilometraje(mantenimiento.get("km_proximo"))
        mantenimiento["establecimiento"] = mantenimiento.get("establecimiento") or mantenimiento.get("taller") or mantenimiento.get("registrado_por_establecimiento") or "VINOVA"
        mantenimientos.append(mantenimiento)

    cursor.execute("""
        SELECT COUNT(*)
        FROM mantenimientos
        WHERE COALESCE(anulado, 0) = 0
    """)
    total_mantenimientos = cursor.fetchone()[0]

    trabajador_establecimiento = obtener_establecimiento_usuario(
        cursor,
        session.get("usuario_id")
    )

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
        vehiculos_clientes=vehiculos_clientes,
        mantenimientos=mantenimientos,
        total_mantenimientos=total_mantenimientos,
        trabajador_establecimiento=trabajador_establecimiento,
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

    asegurar_migraciones_admin()

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

        vehiculo["kilometraje"] = (
            kilometraje_inicial
            if kilometraje_inicial is not None
            else kilometraje_catalogo
        )

        vehiculo["kilometraje_actual"] = vehiculo["kilometraje"]

        vehiculo["imagen"] = obtener_nombre_imagen_vehiculo(
            vehiculo.get("imagen")
        )

        mis_vehiculos.append(vehiculo)

    cursor.execute("""
        SELECT
            mantenimientos.*,
            COALESCE(mantenimientos.kilometraje_actual, mantenimientos.kilometraje) AS km_servicio,
            COALESCE(mantenimientos.proximo_kilometraje, mantenimientos.proximo_servicio_km) AS km_proximo,
            COALESCE(mantenimientos.proxima_fecha, mantenimientos.proximo_servicio_fecha) AS fecha_proxima,
            COALESCE(NULLIF(TRIM(mantenimientos.establecimiento), ''), mantenimientos.taller) AS sede_servicio,
            COALESCE(NULLIF(TRIM(mantenimientos.observaciones), ''), mantenimientos.descripcion) AS detalle_servicio,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            vehiculos.tipo_vehiculo,
            vehiculos.transmision,
            registrador.nombre AS registrado_por_nombre,
            registrador.correo AS registrado_por_correo,
            registrador.rol AS registrado_por_rol,
            registrador.establecimiento AS registrado_por_establecimiento
        FROM mantenimientos
        INNER JOIN vehiculos
            ON vehiculos.id = mantenimientos.vehiculo_id
        LEFT JOIN usuarios AS registrador
            ON registrador.id = mantenimientos.registrado_por
        WHERE mantenimientos.usuario_id = ?
          AND COALESCE(mantenimientos.anulado, 0) = 0
        ORDER BY DATE(mantenimientos.fecha_servicio) DESC, mantenimientos.id DESC
    """, (
        session["usuario_id"],
    ))

    historial_mantenimientos = []

    for fila in cursor.fetchall():
        mantenimiento = dict(fila)
        mantenimiento["fecha_visible"] = formatear_fecha_visible(
            mantenimiento.get("fecha_servicio")
        )
        mantenimiento["proxima_fecha"] = mantenimiento.get("fecha_proxima")
        mantenimiento["proxima_fecha_visible"] = formatear_fecha_visible(
            mantenimiento.get("fecha_proxima")
        )
        mantenimiento["proximo_kilometraje"] = normalizar_kilometraje(
            mantenimiento.get("km_proximo")
        )
        mantenimiento["kilometraje_actual"] = normalizar_kilometraje(
            mantenimiento.get("km_servicio")
        )
        mantenimiento["kilometraje"] = mantenimiento["kilometraje_actual"]
        mantenimiento["proximo_servicio_fecha"] = mantenimiento.get("fecha_proxima")
        mantenimiento["proximo_servicio_fecha_visible"] = mantenimiento["proxima_fecha_visible"]
        mantenimiento["proximo_servicio_km"] = mantenimiento["proximo_kilometraje"]
        mantenimiento["costo"] = normalizar_precio(
            mantenimiento.get("costo")
        ) or 0
        mantenimiento["establecimiento"] = mantenimiento.get("sede_servicio") or ""
        mantenimiento["observaciones"] = mantenimiento.get("detalle_servicio") or ""
        historial_mantenimientos.append(mantenimiento)

    vehiculos_por_id = {vehiculo["id"]: vehiculo for vehiculo in mis_vehiculos}

    for mantenimiento in historial_mantenimientos:
        vehiculo = vehiculos_por_id.get(mantenimiento["vehiculo_id"])

        if not vehiculo:
            continue

        km_mantenimiento = mantenimiento.get("kilometraje_actual")

        if km_mantenimiento is not None:
            km_actual = vehiculo.get("kilometraje_actual")

            if km_actual is None or km_mantenimiento > km_actual:
                vehiculo["kilometraje_actual"] = km_mantenimiento

    servicios_proximos = []

    for mantenimiento in historial_mantenimientos:
        proxima_fecha = mantenimiento.get("proxima_fecha")
        proximo_kilometraje = mantenimiento.get("proximo_kilometraje")

        if not proxima_fecha and proximo_kilometraje is None:
            continue

        vehiculo = vehiculos_por_id.get(mantenimiento["vehiculo_id"], {})
        km_actual = vehiculo.get("kilometraje_actual")
        estado, estado_texto, detalle = estado_programacion_mantenimiento(
            proxima_fecha,
            proximo_kilometraje,
            km_actual
        )

        servicio = dict(mantenimiento)
        servicio["estado"] = estado
        servicio["estado_texto"] = estado_texto
        servicio["detalle_programacion"] = detalle
        servicios_proximos.append(servicio)

    prioridad_estado = {"vencido": 0, "proximo": 1, "programado": 2}
    servicios_proximos.sort(
        key=lambda servicio: (
            prioridad_estado.get(servicio.get("estado"), 9),
            servicio.get("proxima_fecha") or "9999-12-31",
            servicio.get("proximo_kilometraje") or 999999999
        )
    )

    manuales_usuario = []
    ids_vehiculos = [vehiculo["id"] for vehiculo in mis_vehiculos]

    if ids_vehiculos:
        placeholders = ",".join("?" for _ in ids_vehiculos)
        cursor.execute(f"""
            SELECT
                manuales_vehiculo.*,
                vehiculos.codigo_catalogo,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio
            FROM manuales_vehiculo
            INNER JOIN vehiculos
                ON vehiculos.id = manuales_vehiculo.vehiculo_id
            WHERE manuales_vehiculo.vehiculo_id IN ({placeholders})
              AND COALESCE(manuales_vehiculo.activo, 1) = 1
            ORDER BY vehiculos.marca, vehiculos.modelo, manuales_vehiculo.id DESC
        """, ids_vehiculos)

        for fila in cursor.fetchall():
            manual = dict(fila)
            manual["creado_visible"] = formatear_fecha_visible(manual.get("creado_en"))
            manuales_usuario.append(manual)

    conexion.close()

    ultimo_mantenimiento = historial_mantenimientos[0] if historial_mantenimientos else None
    proximo_mantenimiento = servicios_proximos[0] if servicios_proximos else None
    total_alertas = sum(1 for servicio in servicios_proximos if servicio.get("estado") == "vencido")

    return render_template(
        "profile.html",
        nombre=session["usuario"],
        rol=session["rol"],
        foto_perfil=session.get("foto_perfil"),
        mis_vehiculos=mis_vehiculos,
        historial_mantenimientos=historial_mantenimientos,
        servicios_proximos=servicios_proximos,
        ultimo_mantenimiento=ultimo_mantenimiento,
        proximo_mantenimiento=proximo_mantenimiento,
        total_alertas_mantenimiento=total_alertas,
        manuales_usuario=manuales_usuario
    )


@app.route("/perfil/mantenimiento/registrar", methods=["POST"])
@login_required
def registrar_mantenimiento():
    flash("Los mantenimientos de VINOVA son registrados por un trabajador autorizado.", "warning")
    return redirect("/perfil#seccion-historial")


@app.route("/perfil/mantenimiento/<int:mantenimiento_id>/eliminar", methods=["POST"])
@login_required
def eliminar_mantenimiento(mantenimiento_id):
    flash("El historial de mantenimiento solo puede ser anulado por personal de VINOVA.", "warning")
    return redirect("/perfil#seccion-historial")



# ================= MANTENIMIENTO EMPRESARIAL =================

@app.route("/mantenimientos/buscar-vehiculos")
@login_required
@personal_required
def buscar_vehiculos_mantenimiento():

    asegurar_migraciones_admin()

    consulta = request.args.get("q", "").strip()
    limite = request.args.get("limit", 20, type=int) or 20
    limite = max(1, min(limite, 30))

    if len(consulta) < 2 and not consulta.isdigit():
        return jsonify({
            "resultados": [],
            "mensaje": "Escribe al menos 2 caracteres o un ID para buscar por correo, cliente, código o vehículo."
        })

    like = f"%{consulta}%"
    consulta_numerica = consulta if consulta.isdigit() else None
    consulta_id = int(consulta_numerica) if consulta_numerica else -1

    filtros = [
        "LOWER(usuarios.correo) LIKE LOWER(?)",
        "LOWER(usuarios.nombre) LIKE LOWER(?)",
        "LOWER(vehiculos.codigo_catalogo) LIKE LOWER(?)",
        "LOWER(vehiculos.marca) LIKE LOWER(?)",
        "LOWER(vehiculos.modelo) LIKE LOWER(?)",
        "CAST(vehiculos.anio AS TEXT) LIKE ?",
        "LOWER(COALESCE(codigos_vehiculo.codigo, '')) LIKE LOWER(?)"
    ]
    parametros = [like, like, like, like, like, like, like]

    if consulta_numerica:
        filtros.extend([
            "usuarios_vehiculos.id = ?",
            "usuarios.id = ?",
            "vehiculos.id = ?"
        ])
        parametros.extend([int(consulta_numerica), int(consulta_numerica), int(consulta_numerica)])

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(f"""
        SELECT
            usuarios_vehiculos.id AS usuario_vehiculo_id,
            usuarios_vehiculos.usuario_id,
            usuarios_vehiculos.vehiculo_id,
            usuarios_vehiculos.kilometraje_inicial,
            usuarios_vehiculos.fecha_registro,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            vehiculos.kilometraje AS vehiculo_kilometraje,
            codigos_vehiculo.codigo AS codigo_canje,
            COALESCE(
                MAX(mantenimientos.kilometraje_actual),
                usuarios_vehiculos.kilometraje_inicial,
                vehiculos.kilometraje,
                0
            ) AS kilometraje_referencia
        FROM usuarios_vehiculos
        INNER JOIN usuarios
            ON usuarios.id = usuarios_vehiculos.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = usuarios_vehiculos.vehiculo_id
        LEFT JOIN codigos_vehiculo
            ON codigos_vehiculo.id = usuarios_vehiculos.codigo_vehiculo_id
        LEFT JOIN mantenimientos
            ON mantenimientos.usuario_vehiculo_id = usuarios_vehiculos.id
           AND COALESCE(mantenimientos.anulado, 0) = 0
        WHERE ({" OR ".join(filtros)})
        GROUP BY usuarios_vehiculos.id
        ORDER BY
            CASE
                WHEN usuarios_vehiculos.id = ? THEN 0
                WHEN vehiculos.id = ? THEN 1
                WHEN LOWER(usuarios.correo) = LOWER(?) THEN 2
                ELSE 3
            END,
            usuarios.nombre ASC,
            usuarios_vehiculos.id DESC
        LIMIT ?
    """, (*parametros, consulta_id, consulta_id, consulta, limite))

    resultados = []

    for fila in cursor.fetchall():
        kilometraje = normalizar_kilometraje(fila["kilometraje_referencia"])
        vehiculo_texto = f"{fila['marca']} {fila['modelo']} {fila['anio']}".strip()
        codigo_catalogo = fila["codigo_catalogo"] or "Sin código público"
        codigo_canje = fila["codigo_canje"] or "Sin código de canje"

        resultados.append({
            "usuario_vehiculo_id": fila["usuario_vehiculo_id"],
            "usuario_id": fila["usuario_id"],
            "vehiculo_id": fila["vehiculo_id"],
            "usuario_nombre": fila["usuario_nombre"] or "Cliente sin nombre",
            "usuario_correo": fila["usuario_correo"] or "Sin correo",
            "vehiculo": vehiculo_texto,
            "codigo_catalogo": codigo_catalogo,
            "codigo_canje": codigo_canje,
            "kilometraje_referencia": kilometraje or 0,
            "kilometraje_referencia_visible": f"{kilometraje or 0:,}".replace(",", "."),
            "fecha_registro": formatear_fecha_visible(fila["fecha_registro"]),
            "label": f"{fila['usuario_nombre'] or 'Cliente'} — {vehiculo_texto}",
            "detalle": f"Correo: {fila['usuario_correo'] or 'N/D'} · ID vehículo: {fila['vehiculo_id']} · Registro: {fila['usuario_vehiculo_id']} · {codigo_catalogo} · {kilometraje or 0:,} km".replace(",", ".")
        })

    conexion.close()

    return jsonify({
        "resultados": resultados,
        "total": len(resultados)
    })


@app.route("/mantenimientos/registrar", methods=["POST"])
@login_required
@personal_required
def registrar_mantenimiento_empresarial():

    asegurar_migraciones_admin()

    usuario_vehiculo_id = request.form.get("usuario_vehiculo_id", type=int)
    tipo_servicio = request.form.get("tipo_servicio", "").strip()
    fecha_servicio = normalizar_fecha(request.form.get("fecha_servicio"))
    kilometraje_actual = normalizar_kilometraje(request.form.get("kilometraje_actual"))
    costo = normalizar_precio(request.form.get("costo", "0"))
    descripcion = request.form.get("descripcion", "").strip()
    observaciones = request.form.get("observaciones", "").strip()
    establecimiento_form = request.form.get("establecimiento", "").strip()
    origen = request.form.get("origen", "trabajador").strip().lower()

    destino = "/admin/vehiculos#admin-mantenimientos" if origen == "admin" else "/trabajador#trabajador-mantenimientos"

    if not usuario_vehiculo_id:
        flash("Selecciona el vehículo del usuario.", "warning")
        return redirect(destino)

    if not tipo_servicio:
        flash("Indica el tipo de servicio realizado.", "warning")
        return redirect(destino)

    if not fecha_servicio:
        flash("Ingresa una fecha válida para el mantenimiento.", "warning")
        return redirect(destino)

    if kilometraje_actual is None:
        flash("Ingresa un kilometraje actual válido.", "warning")
        return redirect(destino)

    if costo is None:
        costo = 0

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT
                usuarios_vehiculos.id AS usuario_vehiculo_id,
                usuarios_vehiculos.usuario_id,
                usuarios_vehiculos.vehiculo_id,
                usuarios.nombre AS usuario_nombre,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio
            FROM usuarios_vehiculos
            INNER JOIN usuarios
                ON usuarios.id = usuarios_vehiculos.usuario_id
            INNER JOIN vehiculos
                ON vehiculos.id = usuarios_vehiculos.vehiculo_id
            WHERE usuarios_vehiculos.id = ?
            LIMIT 1
        """, (
            usuario_vehiculo_id,
        ))

        registro = cursor.fetchone()

        if not registro:
            flash("El vehículo registrado del usuario no existe.", "warning")
            return redirect(destino)

        establecimiento_trabajador = obtener_establecimiento_usuario(
            cursor,
            session.get("usuario_id")
        )
        establecimiento = establecimiento_trabajador or establecimiento_form or "VINOVA"

        calculo = calcular_proximo_mantenimiento(
            tipo_servicio,
            kilometraje_actual,
            fecha_servicio
        )

        ahora = fecha_actual()

        cursor.execute("""
            INSERT INTO mantenimientos (
                usuario_id,
                vehiculo_id,
                usuario_vehiculo_id,
                registrado_por,
                tipo_servicio,
                descripcion,
                kilometraje_actual,
                fecha_servicio,
                intervalo_km,
                intervalo_meses,
                proximo_kilometraje,
                proxima_fecha,
                observaciones,
                establecimiento,
                estado,
                costo,
                taller,
                kilometraje,
                proximo_servicio_fecha,
                proximo_servicio_km,
                creado_en,
                actualizado_en,
                anulado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            registro["usuario_id"],
            registro["vehiculo_id"],
            registro["usuario_vehiculo_id"],
            session.get("usuario_id"),
            tipo_servicio,
            descripcion,
            kilometraje_actual,
            fecha_servicio,
            calculo["intervalo_km"],
            calculo["intervalo_meses"],
            calculo["proximo_kilometraje"],
            calculo["proxima_fecha"],
            observaciones,
            establecimiento,
            "Realizado",
            costo,
            establecimiento,
            kilometraje_actual,
            calculo["proxima_fecha"],
            calculo["proximo_kilometraje"],
            ahora,
            ahora
        ))

        conexion.commit()
        flash("Mantenimiento registrado correctamente con próxima revisión calculada.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al registrar mantenimiento empresarial:", error)
        flash("No se pudo registrar el mantenimiento.", "error")

    finally:
        conexion.close()

    return redirect(destino)


@app.route("/mantenimientos/<int:mantenimiento_id>/anular", methods=["POST"])
@login_required
@personal_required
def anular_mantenimiento_empresarial(mantenimiento_id):

    asegurar_migraciones_admin()

    motivo = request.form.get("motivo_anulacion", "").strip()
    origen = request.form.get("origen", "trabajador").strip().lower()
    destino = "/admin/vehiculos#admin-mantenimientos" if origen == "admin" else "/trabajador#trabajador-mantenimientos"
    rol = str(session.get("rol", "")).upper()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, registrado_por, COALESCE(anulado, 0) AS anulado
            FROM mantenimientos
            WHERE id = ?
        """, (
            mantenimiento_id,
        ))

        mantenimiento = cursor.fetchone()

        if not mantenimiento:
            flash("Mantenimiento no encontrado.", "warning")
            return redirect(destino)

        if mantenimiento["anulado"] == 1:
            flash("Este mantenimiento ya está anulado.", "warning")
            return redirect(destino)

        if rol != "ADMIN" and mantenimiento["registrado_por"] != session.get("usuario_id"):
            flash("Solo puedes anular mantenimientos registrados por tu propia cuenta.", "warning")
            return redirect(destino)

        cursor.execute("""
            UPDATE mantenimientos
            SET
                anulado = 1,
                anulado_por = ?,
                anulado_en = ?,
                motivo_anulacion = ?,
                estado = 'Anulado',
                actualizado_en = ?
            WHERE id = ?
        """, (
            session.get("usuario_id"),
            fecha_actual(),
            motivo or "Anulado desde panel VINOVA",
            fecha_actual(),
            mantenimiento_id
        ))

        conexion.commit()
        flash("Mantenimiento anulado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al anular mantenimiento:", error)
        flash("No se pudo anular el mantenimiento.", "error")

    finally:
        conexion.close()

    return redirect(destino)


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

    # La selección de cliente/vehículo para mantenimiento ahora se hace por búsqueda AJAX.
    # No cargamos todos los registros aquí para evitar listas enormes cuando haya miles de clientes.
    vehiculos_clientes = []

    cursor.execute("""
        SELECT
            mantenimientos.*,
            COALESCE(mantenimientos.kilometraje_actual, mantenimientos.kilometraje) AS km_servicio,
            COALESCE(mantenimientos.proximo_kilometraje, mantenimientos.proximo_servicio_km) AS km_proximo,
            COALESCE(mantenimientos.proxima_fecha, mantenimientos.proximo_servicio_fecha) AS fecha_proxima,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            registrador.nombre AS registrado_por_nombre,
            registrador.correo AS registrado_por_correo,
            registrador.rol AS registrado_por_rol,
            registrador.establecimiento AS registrado_por_establecimiento
        FROM mantenimientos
        INNER JOIN usuarios
            ON usuarios.id = mantenimientos.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = mantenimientos.vehiculo_id
        LEFT JOIN usuarios AS registrador
            ON registrador.id = mantenimientos.registrado_por
        WHERE COALESCE(mantenimientos.anulado, 0) = 0
        ORDER BY DATE(mantenimientos.fecha_servicio) DESC, mantenimientos.id DESC
        LIMIT 120
    """)
    mantenimientos = []

    for fila in cursor.fetchall():
        mantenimiento = dict(fila)
        mantenimiento["fecha_visible"] = formatear_fecha_visible(mantenimiento.get("fecha_servicio"))
        mantenimiento["proxima_fecha"] = mantenimiento.get("fecha_proxima")
        mantenimiento["proxima_fecha_visible"] = formatear_fecha_visible(mantenimiento.get("fecha_proxima"))
        mantenimiento["kilometraje_actual"] = normalizar_kilometraje(mantenimiento.get("km_servicio"))
        mantenimiento["proximo_kilometraje"] = normalizar_kilometraje(mantenimiento.get("km_proximo"))
        mantenimiento["establecimiento"] = mantenimiento.get("establecimiento") or mantenimiento.get("taller") or mantenimiento.get("registrado_por_establecimiento") or "VINOVA"
        mantenimientos.append(mantenimiento)

    cursor.execute("""
        SELECT COUNT(*)
        FROM mantenimientos
        WHERE COALESCE(anulado, 0) = 0
    """)
    total_mantenimientos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            manuales_vehiculo.*,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            usuarios.nombre AS subido_por_nombre
        FROM manuales_vehiculo
        INNER JOIN vehiculos
            ON vehiculos.id = manuales_vehiculo.vehiculo_id
        LEFT JOIN usuarios
            ON usuarios.id = manuales_vehiculo.subido_por
        ORDER BY manuales_vehiculo.id DESC
    """)
    manuales_admin = cursor.fetchall()

    cursor.execute("""
        SELECT
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.rol,
            usuarios.foto_perfil,
            usuarios.establecimiento,
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
            usuarios.establecimiento,
            COALESCE(usuarios.activo, 1) AS activo,
            usuarios.creado_en,
            usuarios.actualizado_en
        FROM usuarios
        WHERE usuarios.rol = 'TRABAJADOR'
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
        codigos_por_vehiculo=codigos_por_vehiculo,
        vehiculos_clientes=vehiculos_clientes,
        mantenimientos=mantenimientos,
        total_mantenimientos=total_mantenimientos,
        manuales_admin=manuales_admin
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
    establecimiento = request.form.get("establecimiento", "").strip()

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
                creado_en,
                establecimiento
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            nombre,
            correo,
            password_hash,
            rol,
            1,
            ahora,
            establecimiento if rol == "TRABAJADOR" else ""
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



@app.route("/admin/trabajadores/<int:trabajador_id>/establecimiento", methods=["POST"])
@login_required
@admin_required
def admin_actualizar_establecimiento_trabajador(trabajador_id):

    asegurar_migraciones_admin()

    establecimiento = request.form.get("establecimiento", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, rol
            FROM usuarios
            WHERE id = ?
        """, (
            trabajador_id,
        ))

        trabajador = cursor.fetchone()

        if not trabajador:
            flash("Trabajador no encontrado.", "warning")
            return redirigir_admin("trabajadores")

        if trabajador["rol"] != "TRABAJADOR":
            flash("El establecimiento solo se asigna a cuentas de trabajador.", "warning")
            return redirigir_admin("trabajadores")

        cursor.execute("""
            UPDATE usuarios
            SET establecimiento = ?, actualizado_en = ?
            WHERE id = ?
        """, (
            establecimiento,
            fecha_actual(),
            trabajador_id
        ))

        conexion.commit()
        flash("Establecimiento del trabajador actualizado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar establecimiento:", error)
        flash("No se pudo actualizar el establecimiento.", "error")

    finally:
        conexion.close()

    return redirigir_admin("trabajadores")


@app.route("/admin/manuales/guardar", methods=["POST"])
@login_required
@admin_required
def admin_guardar_manual_vehiculo():

    asegurar_migraciones_admin()

    vehiculo_id = request.form.get("vehiculo_id", type=int)
    titulo = request.form.get("titulo", "").strip()
    tipo_documento = request.form.get("tipo_documento", "Manual").strip()
    enlace = request.form.get("enlace", "").strip()
    archivo = request.form.get("archivo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not vehiculo_id:
        flash("Selecciona el vehículo al que pertenece el manual.", "warning")
        return redirigir_admin("manuales")

    if not titulo:
        flash("El título del manual es obligatorio.", "warning")
        return redirigir_admin("manuales")

    if not enlace and not archivo:
        flash("Agrega un enlace externo o una ruta de archivo local para el manual.", "warning")
        return redirigir_admin("manuales")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id FROM vehiculos WHERE id = ?", (vehiculo_id,))

        if not cursor.fetchone():
            flash("Vehículo no encontrado.", "warning")
            return redirigir_admin("manuales")

        cursor.execute("""
            INSERT INTO manuales_vehiculo (
                vehiculo_id,
                titulo,
                tipo_documento,
                archivo,
                enlace,
                descripcion,
                subido_por,
                creado_en,
                activo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            vehiculo_id,
            titulo,
            tipo_documento,
            archivo,
            enlace,
            descripcion,
            session.get("usuario_id"),
            fecha_actual()
        ))

        conexion.commit()
        flash("Manual asignado al vehículo correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar manual:", error)
        flash("No se pudo guardar el manual.", "error")

    finally:
        conexion.close()

    return redirigir_admin("manuales")


@app.route("/admin/manuales/<int:manual_id>/estado", methods=["POST"])
@login_required
@admin_required
def admin_cambiar_estado_manual(manual_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, COALESCE(activo, 1) AS activo
            FROM manuales_vehiculo
            WHERE id = ?
        """, (
            manual_id,
        ))

        manual = cursor.fetchone()

        if not manual:
            flash("Manual no encontrado.", "warning")
            return redirigir_admin("manuales")

        nuevo_estado = 0 if manual["activo"] == 1 else 1

        cursor.execute("""
            UPDATE manuales_vehiculo
            SET activo = ?
            WHERE id = ?
        """, (
            nuevo_estado,
            manual_id
        ))

        conexion.commit()

        if nuevo_estado == 1:
            flash("Manual activado correctamente.", "success")
        else:
            flash("Manual ocultado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar estado del manual:", error)
        flash("No se pudo actualizar el manual.", "error")

    finally:
        conexion.close()

    return redirigir_admin("manuales")


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