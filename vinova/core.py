from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify, send_from_directory, abort
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
import smtplib
import ssl
import hashlib
import json
import threading
from email.message import EmailMessage
from dotenv import load_dotenv
from markupsafe import Markup
import cloudinary
import cloudinary.uploader
from PIL import Image, UnidentifiedImageError


load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    raise RuntimeError("Falta configurar FLASK_SECRET_KEY en el archivo .env")
app.secret_key = FLASK_SECRET_KEY
app.permanent_session_lifetime = timedelta(days=1)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "80")) * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_COOKIE_SECURE", "0") == "1"


# ================= CONFIGURACIÓN DE ARCHIVOS LOCALES =================
# Las imágenes de vehículos del catálogo se guardan localmente.
# Las fotos de perfil siguen usando Cloudinary.

app.config["VEHICLE_IMAGE_FOLDER"] = os.path.join(
    BASE_DIR,
    "static",
    "img",
    "vehicles"
)

app.config["VEHICLE_3D_FOLDER"] = os.path.join(
    BASE_DIR,
    "static",
    "models",
    "vehicles"
)

app.config["MANUALS_FOLDER"] = os.path.join(
    BASE_DIR,
    "static",
    "docs",
    "manuales"
)

app.config["INVOICE_FOLDER"] = os.path.join(
    BASE_DIR,
    "static",
    "docs",
    "facturas"
)

os.makedirs(app.config["VEHICLE_IMAGE_FOLDER"], exist_ok=True)
os.makedirs(app.config["VEHICLE_3D_FOLDER"], exist_ok=True)
os.makedirs(app.config["MANUALS_FOLDER"], exist_ok=True)
os.makedirs(app.config["INVOICE_FOLDER"], exist_ok=True)

EXTENSIONES_IMAGEN_VEHICULO = {"jpg", "jpeg", "png", "webp"}
EXTENSIONES_DOCUMENTO = {"pdf", "jpg", "jpeg", "png", "webp"}
EXTENSIONES_MODELO_3D = {"glb", "gltf"}


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
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "0") == "1"

ROLES_CREABLES_DESDE_PANEL = {"USUARIO", "TRABAJADOR"}


# ================= CONFIGURACIÓN DE CORREOS =================
# Por decisión del proyecto, VINOVA conserva la estructura de correos,
# pero por defecto trabaja en modo simulado para no depender de Gmail,
# Outlook u otro proveedor SMTP durante el desarrollo y la exposición.
#
# EMAIL_MODE=simulado  -> no envía correos reales; imprime el correo en consola.
# EMAIL_MODE=smtp      -> intenta enviar correos reales usando SMTP.

EMAIL_MODE = os.getenv("EMAIL_MODE", "simulado").strip().lower() or "simulado"
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER or "noreply@vinova.local").strip()
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "VINOVA").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1") == "1"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "0") == "1"
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", SMTP_FROM_EMAIL).strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30") or 30)


# ================= CONFIGURACIÓN DE CLOUDINARY =================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


# ================= FUNCIONES AUXILIARES =================

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "vinova.db"))

def conectar_db():
    conexion = sqlite3.connect(DATABASE_PATH)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion



def registrar_auditoria(conexion, accion, entidad=None, entidad_id=None, detalle=None):
    """Registra acciones importantes sin interrumpir la operación principal."""

    if not conexion or not accion:
        return

    try:
        cursor = conexion.cursor()

        if isinstance(detalle, (dict, list, tuple)):
            detalle_texto = json.dumps(detalle, ensure_ascii=False, default=str)
        elif detalle is None:
            detalle_texto = ""
        else:
            detalle_texto = str(detalle)

        cursor.execute("""
            INSERT INTO auditoria_acciones (
                usuario_id, usuario_nombre, usuario_rol, accion, entidad, entidad_id,
                detalle, ip, user_agent, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("usuario_id"),
            session.get("usuario"),
            session.get("rol"),
            str(accion)[:120],
            str(entidad or "")[:80],
            entidad_id,
            detalle_texto[:4000],
            obtener_ip_cliente(),
            request.headers.get("User-Agent", "")[:500],
            fecha_actual()
        ))
    except Exception as error:
        print("Advertencia: no se pudo registrar auditoría:", error)


def correo_en_modo_simulado():
    return EMAIL_MODE != "smtp"


def smtp_configurado():
    return bool(SMTP_HOST and SMTP_FROM_EMAIL and (SMTP_PASSWORD or not SMTP_USER))


def construir_url_absoluta(endpoint, **valores):
    """Crea enlaces absolutos para correos aunque se ejecute en local."""

    if APP_BASE_URL:
        return f"{APP_BASE_URL}{url_for(endpoint, **valores)}"

    try:
        return url_for(endpoint, _external=True, **valores)
    except RuntimeError:
        return url_for(endpoint, **valores)


def enviar_correo(destinatario, asunto, texto, html_contenido=None, reply_to=None):
    """Gestiona correos de VINOVA.

    En modo simulado no conecta con proveedores externos. Solo imprime el
    contenido en consola para mantener la estructura del sistema sin depender
    de credenciales SMTP reales.
    """

    destinatario = str(destinatario or "").strip()

    if not destinatario or "@" not in destinatario:
        return False

    if correo_en_modo_simulado():
        print("\n================= CORREO VINOVA SIMULADO =================")
        print(f"Para: {destinatario}")
        print(f"Asunto: {asunto}")
        if reply_to:
            print(f"Responder a: {reply_to}")
        print("-----------------------------------------------------------")
        print(texto or "")
        print("===========================================================\n")
        return True

    if not smtp_configurado():
        print("Correo no enviado: falta configuración SMTP.")
        print(f"Para: {destinatario} | Asunto: {asunto}")
        return False

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    mensaje["To"] = destinatario

    if reply_to:
        mensaje["Reply-To"] = reply_to

    mensaje.set_content(texto or "")

    if html_contenido:
        mensaje.add_alternative(html_contenido, subtype="html")

    try:
        if SMTP_USE_SSL:
            contexto = ssl.create_default_context()

            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=contexto, timeout=20) as servidor:
                if SMTP_USER:
                    servidor.login(SMTP_USER, SMTP_PASSWORD)

                servidor.send_message(mensaje)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as servidor:
                if SMTP_USE_TLS:
                    servidor.starttls(context=ssl.create_default_context())

                if SMTP_USER:
                    servidor.login(SMTP_USER, SMTP_PASSWORD)

                servidor.send_message(mensaje)

        return True

    except Exception as error:
        print("Error al enviar correo:", error)
        return False


def plantilla_correo(titulo, contenido_html, texto_boton=None, url_boton=None):
    boton = ""

    if texto_boton and url_boton:
        boton = (
            '<p style="margin:28px 0;">'
            f'<a href="{html.escape(url_boton, quote=True)}" '
            'style="background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700;display:inline-block;">'
            f'{html.escape(texto_boton)}'
            '</a></p>'
        )

    return (
        '<div style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">'
        '<div style="max-width:640px;margin:0 auto;padding:28px 16px;">'
        '<div style="background:#040b17;color:#ffffff;border-radius:18px 18px 0 0;padding:24px 28px;">'
        '<h1 style="margin:0;font-size:26px;letter-spacing:.04em;">VINOVA</h1>'
        '<p style="margin:6px 0 0;color:#bfdbfe;">Plataforma automotriz comercial</p>'
        '</div>'
        '<div style="background:#ffffff;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 18px 18px;padding:28px;">'
        f'<h2 style="margin:0 0 14px;color:#0f172a;font-size:22px;">{html.escape(titulo)}</h2>'
        '<div style="font-size:15px;line-height:1.65;color:#334155;">'
        f'{contenido_html}'
        '</div>'
        f'{boton}'
        '<p style="margin:30px 0 0;color:#64748b;font-size:12px;line-height:1.5;">'
        'Este mensaje fue generado automáticamente por VINOVA. Si no reconoces esta actividad, contacta con administración.'
        '</p></div></div></div>'
    )


def usuario_permite_correo(fila_usuario, categoria="general"):
    if not fila_usuario:
        return False

    def valor_columna(nombre, defecto=1):
        try:
            if nombre in fila_usuario.keys():
                valor = fila_usuario[nombre]
                return defecto if valor is None else int(valor)
        except Exception:
            pass

        return defecto

    if valor_columna("notificar_correo", 1) != 1:
        return False

    if categoria == "mantenimiento":
        return valor_columna("notificar_mantenimientos", 1) == 1

    if categoria == "alerta":
        return valor_columna("notificar_alertas", 1) == 1

    if categoria == "factura":
        return valor_columna("notificar_facturas", 1) == 1

    return True


def enviar_correo_usuario(fila_usuario, categoria, asunto, texto, html_contenido):
    if not fila_usuario or not usuario_permite_correo(fila_usuario, categoria):
        return False

    return enviar_correo(fila_usuario["correo"], asunto, texto, html_contenido)


def generar_hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def extension_permitida(nombre_archivo, extensiones):
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in extensiones


def reiniciar_stream_archivo(archivo):
    try:
        archivo.stream.seek(0)
    except Exception:
        try:
            archivo.seek(0)
        except Exception:
            pass


def obtener_extension_archivo(nombre_archivo):
    return str(nombre_archivo or "").rsplit(".", 1)[-1].lower()


def validar_archivo_imagen_real(archivo):
    """Comprueba con Pillow que el archivo subido sea una imagen real."""

    if not archivo or not getattr(archivo, "filename", ""):
        raise ValueError("No se recibió una imagen válida.")

    extension = obtener_extension_archivo(archivo.filename)
    formatos_por_extension = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
    }

    formato_esperado = formatos_por_extension.get(extension)

    if not formato_esperado:
        raise ValueError("Formato de imagen no permitido. Usa JPG, PNG o WEBP.")

    try:
        reiniciar_stream_archivo(archivo)

        with Image.open(archivo.stream) as imagen:
            formato_real = (imagen.format or "").upper()
            imagen.verify()

        if formato_real != formato_esperado:
            raise ValueError("La extensión del archivo no coincide con el contenido real de la imagen.")

    except UnidentifiedImageError as error:
        raise ValueError("El archivo subido no es una imagen válida.") from error
    except OSError as error:
        raise ValueError("No se pudo validar la imagen subida. Intenta con otro archivo.") from error
    finally:
        reiniciar_stream_archivo(archivo)


def validar_documento_subido_real(archivo, extension):
    """Valida contenido real de PDF o imagen antes de guardarlo como documento."""

    extension = str(extension or "").lower()

    if extension in EXTENSIONES_IMAGEN_VEHICULO:
        validar_archivo_imagen_real(archivo)
        return

    if extension == "pdf":
        try:
            reiniciar_stream_archivo(archivo)
            encabezado = archivo.stream.read(5)
        finally:
            reiniciar_stream_archivo(archivo)

        if encabezado != b"%PDF-":
            raise ValueError("El archivo subido no es un PDF válido.")

        return

    raise ValueError("Formato de documento no permitido. Usa PDF, JPG, PNG o WEBP.")


def normalizar_ruta_static_documento(ruta):
    """Normaliza rutas locales guardadas dentro de static para manuales/facturas."""

    texto = str(ruta or "").strip().replace("\\", "/")

    if not texto:
        return ""

    texto_lower = texto.lower()

    if texto_lower.startswith("http://") or texto_lower.startswith("https://"):
        return ""

    if texto.startswith("/static/"):
        texto = texto[len("/static/"):]
    elif texto.startswith("static/"):
        texto = texto[len("static/"):]

    texto = texto.lstrip("/")

    if ".." in texto.split("/"):
        return ""

    return texto


def guardar_documento_local(archivo, carpeta_config, prefijo):
    """Guarda un PDF/imagen en static/docs y devuelve la ruta relativa a static."""

    if not archivo or not getattr(archivo, "filename", ""):
        return ""

    nombre_original = secure_filename(archivo.filename)

    if not nombre_original or not extension_permitida(nombre_original, EXTENSIONES_DOCUMENTO):
        raise ValueError("Formato de documento no permitido. Usa PDF, JPG, PNG o WEBP.")

    extension = nombre_original.rsplit(".", 1)[1].lower()
    validar_documento_subido_real(archivo, extension)

    prefijo_seguro = crear_slug(prefijo or "documento")
    nombre_final = f"{prefijo_seguro}-{int(time.time())}-{secrets.token_hex(4)}.{extension}"

    carpeta_destino = app.config[carpeta_config]
    os.makedirs(carpeta_destino, exist_ok=True)

    ruta_destino = os.path.join(carpeta_destino, nombre_final)
    archivo.save(ruta_destino)

    return os.path.relpath(ruta_destino, app.static_folder).replace("\\", "/")


def generar_numero_factura(usuario_vehiculo_id):
    fecha_compacta = datetime.now().strftime("%Y%m%d")
    return f"VNV-FAC-{fecha_compacta}-{int(usuario_vehiculo_id or 0):05d}-{secrets.token_hex(2).upper()}"


def redirigir_operativo(seccion="vehiculos", origen=None):
    """Devuelve al panel correcto según quién hizo la operación."""

    origen = (origen or request.form.get("origen", "admin") or "admin").strip().lower()

    if origen == "trabajador":
        return redirect(f"/trabajador#trabajador-{seccion}")

    return redirect(f"/admin/vehiculos#admin-{seccion}")


def normalizar_modelo_clave(valor):
    texto = str(valor or "").strip().lower()
    texto = texto.replace("á", "a").replace("é", "e").replace("í", "i")
    texto = texto.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def obtener_o_crear_modelo_base(
    cursor,
    marca,
    modelo,
    anio,
    tipo_vehiculo="",
    combustible="",
    transmision="",
    modelo_3d="",
    modelo_3d_id="",
    modelo_3d_tipo="glb",
    preview_sistemas_json="",
    usuario_id=None,
):
    """
    Crea o reutiliza el modelo base del vehículo.
    Unidades iguales, por ejemplo Toyota RAV4 2024, comparten manuales y modelo 3D.
    """

    ahora = fecha_actual()
    marca = str(marca or "").strip()
    modelo = str(modelo or "").strip()
    anio = int(anio)
    tipo_vehiculo = str(tipo_vehiculo or "").strip()
    combustible = str(combustible or "").strip()
    transmision = str(transmision or "").strip()
    modelo_3d = str(modelo_3d or "").strip()
    modelo_3d_id = str(modelo_3d_id or "").strip()
    modelo_3d_tipo = str(modelo_3d_tipo or "glb").strip() or "glb"
    preview_sistemas_json = str(preview_sistemas_json or "").strip()

    cursor.execute("""
        SELECT *
        FROM vehiculo_modelos
        WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
          AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
          AND anio = ?
        LIMIT 1
    """, (marca, modelo, anio))

    fila = cursor.fetchone()

    if fila:
        modelo_id = fila["id"]

        modelo_3d_final = modelo_3d or fila["modelo_3d"] or ""
        modelo_3d_id_final = modelo_3d_id or fila["modelo_3d_id"] or ""
        modelo_3d_tipo_final = modelo_3d_tipo or fila["modelo_3d_tipo"] or "glb"
        preview_sistemas_json_final = preview_sistemas_json or fila["preview_sistemas_json"] or ""

        cursor.execute("""
            UPDATE vehiculo_modelos
            SET
                tipo_vehiculo = COALESCE(NULLIF(TRIM(?), ''), tipo_vehiculo),
                combustible = COALESCE(NULLIF(TRIM(?), ''), combustible),
                transmision = COALESCE(NULLIF(TRIM(?), ''), transmision),
                modelo_3d = ?,
                modelo_3d_id = ?,
                modelo_3d_tipo = ?,
                preview_sistemas_json = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (
            tipo_vehiculo,
            combustible,
            transmision,
            modelo_3d_final,
            modelo_3d_id_final,
            modelo_3d_tipo_final,
            preview_sistemas_json_final,
            ahora,
            modelo_id,
        ))

        return {
            "id": modelo_id,
            "modelo_3d": modelo_3d_final,
            "modelo_3d_id": modelo_3d_id_final,
            "modelo_3d_tipo": modelo_3d_tipo_final,
            "preview_sistemas_json": preview_sistemas_json_final,
        }

    cursor.execute("""
        INSERT INTO vehiculo_modelos (
            marca,
            modelo,
            anio,
            tipo_vehiculo,
            combustible,
            transmision,
            modelo_3d,
            modelo_3d_id,
            modelo_3d_tipo,
            preview_sistemas_json,
            creado_por,
            creado_en,
            actualizado_en,
            activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        marca,
        modelo,
        anio,
        tipo_vehiculo,
        combustible,
        transmision,
        modelo_3d,
        modelo_3d_id,
        modelo_3d_tipo,
        preview_sistemas_json,
        usuario_id,
        ahora,
        ahora,
    ))

    return {
        "id": cursor.lastrowid,
        "modelo_3d": modelo_3d,
        "modelo_3d_id": modelo_3d_id,
        "modelo_3d_tipo": modelo_3d_tipo,
        "preview_sistemas_json": preview_sistemas_json,
    }


def guardar_manual_modelo_desde_form(cursor, modelo_base_id, usuario_id):
    """Guarda manuales ligados al modelo base desde el formulario de vehículo."""

    if not modelo_base_id:
        return

    titulo = request.form.get("manual_titulo", "").strip()
    tipo_documento = request.form.get("manual_tipo_documento", "Manual").strip() or "Manual"
    enlace = request.form.get("manual_enlace", "").strip()
    archivo = normalizar_ruta_static_documento(request.form.get("manual_archivo", ""))
    descripcion = request.form.get("manual_descripcion", "").strip()
    archivo_subido = request.files.get("manual_file")

    if archivo_subido and archivo_subido.filename:
        try:
            archivo = guardar_documento_local(archivo_subido, "MANUALS_FOLDER", f"manual-modelo-{modelo_base_id}-{titulo or 'vinova'}")
        except ValueError as error:
            flash(str(error), "warning")
            return

    if not titulo and not archivo and not enlace:
        return

    if not titulo:
        titulo = "Manual del vehículo"

    cursor.execute("""
        SELECT id
        FROM manuales_modelo
        WHERE modelo_id = ?
          AND LOWER(TRIM(titulo)) = LOWER(TRIM(?))
          AND COALESCE(NULLIF(TRIM(archivo), ''), '') = COALESCE(NULLIF(TRIM(?), ''), '')
          AND COALESCE(NULLIF(TRIM(enlace), ''), '') = COALESCE(NULLIF(TRIM(?), ''), '')
        LIMIT 1
    """, (modelo_base_id, titulo, archivo, enlace))

    if cursor.fetchone():
        return

    cursor.execute("""
        INSERT INTO manuales_modelo (
            modelo_id,
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
        modelo_base_id,
        titulo,
        tipo_documento,
        archivo,
        enlace,
        descripcion,
        usuario_id,
        fecha_actual(),
    ))


def _pdf_escape(valor):
    texto = str(valor or "")
    texto = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    texto = texto.replace("\r", " ").replace("\n", " ")
    return texto


def _pdf_text(x, y, texto, size=10, bold=False):
    font = "F2" if bold else "F1"
    return f"BT /{font} {size} Tf {x} {y} Td ({_pdf_escape(texto)}) Tj ET"


def generar_pdf_factura(datos):
    """
    Genera una factura PDF VINOVA.

    Primero intenta usar la plantilla profesional HTML/CSS:
    - templates/factura_pdf.html
    - static/css/factura_pdf.css
    - static/img/vinova-logo.svg

    Si WeasyPrint o la plantilla fallan, crea un PDF básico de respaldo para que
    la factura no deje de guardarse en el perfil del cliente.
    """

    from pathlib import Path

    numero_factura = (
        str(datos.get("numero_factura") or "").strip().upper()
        or generar_numero_factura(datos.get("usuario_vehiculo_id"))
    )

    nombre_archivo = f"{crear_slug(numero_factura)}.pdf"
    ruta_pdf = os.path.join(app.config["INVOICE_FOLDER"], nombre_archivo)
    os.makedirs(app.config["INVOICE_FOLDER"], exist_ok=True)

    subtotal = normalizar_precio(datos.get("subtotal"))
    impuesto = normalizar_precio(datos.get("impuesto"))
    descuento = normalizar_precio(datos.get("descuento"))
    total = normalizar_precio(datos.get("total"))

    if subtotal is None:
        subtotal = normalizar_precio(datos.get("monto")) or 0

    if impuesto is None:
        impuesto = 0

    if descuento is None:
        descuento = 0

    if total is None:
        total = subtotal + impuesto - descuento

    items = datos.get("items") or []

    if not items:
        items = [
            {
                "descripcion": datos.get("concepto") or datos.get("descripcion") or "Servicio VINOVA",
                "cantidad": 1,
                "precio_unitario": subtotal,
                "total": subtotal
            }
        ]

    factura = {
        "numero_factura": numero_factura,
        "fecha_factura": datos.get("fecha_factura") or datetime.now().strftime("%Y-%m-%d"),
        "hora_factura": datos.get("hora_factura") or datetime.now().strftime("%H:%M"),
        "establecimiento": datos.get("establecimiento") or "VINOVA",
        "tipo_factura": datos.get("tipo_factura") or "Servicio",
        "concepto": datos.get("concepto") or "Servicio VINOVA",
        "descripcion": datos.get("descripcion") or "",
        "observaciones": datos.get("observaciones") or datos.get("descripcion") or "",
        "subtotal": subtotal,
        "impuesto": impuesto,
        "descuento": descuento,
        "total": total
    }

    cliente = {
        "nombre": datos.get("cliente_nombre") or datos.get("usuario_nombre") or "Cliente VINOVA",
        "correo": datos.get("cliente_correo") or datos.get("usuario_correo") or "N/D",
        "cedula": datos.get("cliente_cedula") or datos.get("usuario_cedula") or datos.get("cedula") or "N/D"
    }

    vehiculo = {
        "nombre_completo": datos.get("vehiculo") or "",
        "marca": datos.get("marca") or "",
        "modelo": datos.get("modelo") or "",
        "anio": datos.get("anio") or "",
        "codigo_catalogo": datos.get("codigo_catalogo") or "N/D",
        "placa": datos.get("placa") or "N/D",
        "kilometraje": (
            datos.get("kilometraje")
            or datos.get("kilometraje_actual")
            or datos.get("kilometraje_referencia")
            or "N/D"
        )
    }

    responsable = {
        "nombre": datos.get("generado_por_nombre") or datos.get("responsable_nombre") or "Equipo VINOVA",
        "rol": datos.get("generado_por_rol") or datos.get("responsable_rol") or "Personal VINOVA"
    }

    empresa = {
        "direccion": "Av. De los Granados E11-67 y De las Hiedras, Quito, Pichincha - Ecuador",
        "correo": "info@vinova.ec",
        "telefono": "+593 2 395 8721",
        "web": "www.vinova.com.ec"
    }

    try:
        from weasyprint import HTML

        logo_path = os.path.join(app.static_folder, "img", "vinova-logo.svg")
        css_path = os.path.join(app.static_folder, "css", "factura_pdf.css")

        html_factura = render_template(
            "factura_pdf.html",
            factura=factura,
            cliente=cliente,
            vehiculo=vehiculo,
            responsable=responsable,
            empresa=empresa,
            items=items,
            logo_src=Path(logo_path).as_uri(),
            css_src=Path(css_path).as_uri()
        )

        HTML(
            string=html_factura,
            base_url=BASE_DIR
        ).write_pdf(ruta_pdf)

        return os.path.relpath(ruta_pdf, app.static_folder).replace("\\", "/")

    except Exception as error:
        print("Advertencia: no se pudo generar PDF profesional con WeasyPrint/plantilla:", error)
        print("Se generará PDF básico de respaldo para no perder la factura.")

    # Respaldo básico sin dependencias externas. No usa el mockup, pero garantiza
    # que el cliente reciba la factura en su perfil si WeasyPrint falla.
    cliente_nombre = cliente["nombre"]
    cliente_correo = cliente["correo"]
    vehiculo_texto = (
        vehiculo["nombre_completo"]
        or f"{vehiculo['marca']} {vehiculo['modelo']} {vehiculo['anio']}".strip()
        or "N/D"
    )

    content = []
    content.append("0.015 0.043 0.090 rg 0 742 595 100 re f")
    content.append("0.000 0.471 1.000 rg 0 736 595 6 re f")
    content.append("0.940 0.970 1.000 rg")
    content.append(_pdf_text(44, 790, "VINOVA", 28, True))
    content.append(_pdf_text(44, 770, "Factura generada por el sistema", 10, False))
    content.append(_pdf_text(390, 792, numero_factura, 12, True))
    content.append(_pdf_text(390, 774, f"{factura['fecha_factura']}  {factura['hora_factura']}", 10, False))

    content.append("0.020 0.045 0.090 rg")
    content.append(_pdf_text(44, 700, "Datos del cliente", 14, True))
    content.append(_pdf_text(330, 700, "Datos del vehiculo", 14, True))
    content.append("0.850 0.890 0.960 RG 0.8 w 44 692 m 270 692 l S 330 692 m 560 692 l S")

    content.append(_pdf_text(44, 670, f"Cliente: {cliente_nombre}", 10, False))
    content.append(_pdf_text(44, 652, f"Correo: {cliente_correo}", 10, False))
    content.append(_pdf_text(44, 634, f"Local: {factura['establecimiento']}", 10, False))
    content.append(_pdf_text(44, 616, f"Responsable: {responsable['nombre']}", 10, False))

    content.append(_pdf_text(330, 670, f"Vehiculo: {vehiculo_texto}", 10, False))
    content.append(_pdf_text(330, 652, f"Codigo: {vehiculo['codigo_catalogo']}", 10, False))
    content.append(_pdf_text(330, 634, f"Kilometraje: {vehiculo['kilometraje']}", 10, False))

    content.append("0.965 0.975 0.995 rg 44 455 516 120 re f")
    content.append("0.750 0.820 0.940 RG 1 w 44 455 516 120 re S")
    content.append("0.020 0.045 0.090 rg")
    content.append(_pdf_text(60, 548, "Detalle", 13, True))

    y = 524
    for item in items[:5]:
        item_desc = item.get("descripcion", "Servicio VINOVA")
        item_cant = normalizar_precio(item.get("cantidad")) or 1
        item_unit = normalizar_precio(item.get("precio_unitario")) or 0
        item_total = normalizar_precio(item.get("total")) or (item_cant * item_unit)
        content.append(_pdf_text(60, y, f"{item_desc}  x{item_cant:g}  ${item_total:,.2f}", 10, False))
        y -= 18

    content.append("0.015 0.043 0.090 rg 350 320 210 110 re f")
    content.append("0.940 0.970 1.000 rg")
    content.append(_pdf_text(370, 395, f"Subtotal: ${subtotal:,.2f}", 11, False))
    content.append(_pdf_text(370, 373, f"IVA: ${impuesto:,.2f}", 11, False))
    if descuento:
        content.append(_pdf_text(370, 351, f"Descuento: ${descuento:,.2f}", 11, False))
    content.append("0.000 0.471 1.000 rg 350 340 210 2 re f")
    content.append("1 1 1 rg")
    content.append(_pdf_text(370, 325, f"TOTAL: ${total:,.2f}", 15, True))

    content.append("0.390 0.450 0.560 rg")
    content.append(_pdf_text(44, 70, "VINOVA - Documento generado automaticamente. Conserva este comprobante en tu perfil.", 9, False))
    content.append(_pdf_text(44, 52, "Gracias por confiar en VINOVA.", 8, False))

    stream = "\n".join(content).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n% VINOVA\n")
    offsets = [0]

    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())

    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())

    with open(ruta_pdf, "wb") as archivo_pdf:
        archivo_pdf.write(pdf)

    return os.path.relpath(ruta_pdf, app.static_folder).replace("\\", "/")


def registrar_factura_generada(
    cursor,
    *,
    registro,
    tipo_factura,
    concepto,
    descripcion,
    subtotal,
    impuesto=0,
    descuento=0,
    mantenimiento_id=None,
    numero_factura="",
    fecha_factura=None,
    items=None,
    observaciones=""
):
    """Inserta una factura VINOVA, genera su PDF y la deja visible en el perfil del cliente."""

    fecha_factura = normalizar_fecha(fecha_factura) or datetime.now().strftime("%Y-%m-%d")
    hora_factura = datetime.now().strftime("%H:%M")
    subtotal = normalizar_precio(subtotal) or 0
    impuesto = normalizar_precio(impuesto) or 0
    descuento = normalizar_precio(descuento) or 0
    total = max(0, subtotal + impuesto - descuento)
    numero_factura = (numero_factura or "").strip().upper() or generar_numero_factura(registro.get("usuario_vehiculo_id"))
    establecimiento = obtener_establecimiento_usuario(cursor, session.get("usuario_id")) or registro.get("establecimiento") or "VINOVA"
    ahora = fecha_actual()

    cursor.execute("""
        SELECT nombre, correo, rol, establecimiento
        FROM usuarios
        WHERE id = ?
    """, (session.get("usuario_id"),))
    responsable = cursor.fetchone()

    items_pdf = []

    for item in items or []:
        cantidad = normalizar_precio(item.get("cantidad")) or 1
        precio_unitario = normalizar_precio(item.get("precio_unitario")) or 0
        total_item = normalizar_precio(item.get("total"))

        if total_item is None:
            total_item = cantidad * precio_unitario

        items_pdf.append({
            "descripcion": str(item.get("descripcion") or concepto or "Servicio VINOVA").strip(),
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total_item,
        })

    if not items_pdf:
        items_pdf = [{
            "descripcion": descripcion or concepto or "Servicio VINOVA",
            "cantidad": 1,
            "precio_unitario": subtotal,
            "total": subtotal,
        }]

    datos_pdf = {
        "numero_factura": numero_factura,
        "usuario_vehiculo_id": registro.get("usuario_vehiculo_id"),
        "cliente_nombre": registro.get("usuario_nombre"),
        "cliente_correo": registro.get("usuario_correo"),
        "cliente_cedula": registro.get("usuario_cedula") or registro.get("cedula"),
        "vehiculo": f"{registro.get('marca', '')} {registro.get('modelo', '')} {registro.get('anio', '')}".strip(),
        "marca": registro.get("marca"),
        "modelo": registro.get("modelo"),
        "anio": registro.get("anio"),
        "codigo_catalogo": registro.get("codigo_catalogo") or "N/D",
        "placa": registro.get("placa") or "N/D",
        "concepto": concepto,
        "descripcion": descripcion,
        "observaciones": observaciones or descripcion,
        "tipo_factura": tipo_factura,
        "subtotal": subtotal,
        "impuesto": impuesto,
        "descuento": descuento,
        "total": total,
        "items": items_pdf,
        "fecha_factura": fecha_factura,
        "hora_factura": hora_factura,
        "establecimiento": establecimiento,
        "generado_por_nombre": responsable["nombre"] if responsable else "VINOVA",
        "generado_por_rol": responsable["rol"] if responsable else "Personal VINOVA",
        "kilometraje": registro.get("kilometraje_actual") or registro.get("kilometraje_referencia"),
    }

    archivo_pdf = generar_pdf_factura(datos_pdf)

    cursor.execute("""
        INSERT INTO facturas_vehiculo (
            usuario_id,
            vehiculo_id,
            usuario_vehiculo_id,
            mantenimiento_id,
            numero_factura,
            tipo_factura,
            concepto,
            descripcion,
            archivo,
            archivo_pdf,
            enlace,
            fecha_factura,
            hora_factura,
            monto,
            subtotal,
            impuesto,
            total,
            establecimiento,
            subido_por,
            generado_por,
            creado_en,
            actualizado_en,
            activo,
            estado,
            anulado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'Generada', 0)
    """, (
        registro.get("usuario_id"),
        registro.get("vehiculo_id"),
        registro.get("usuario_vehiculo_id"),
        mantenimiento_id,
        numero_factura,
        tipo_factura,
        concepto,
        descripcion,
        archivo_pdf,
        archivo_pdf,
        fecha_factura,
        hora_factura,
        total,
        subtotal,
        impuesto,
        total,
        establecimiento,
        session.get("usuario_id"),
        session.get("usuario_id"),
        ahora,
        ahora,
    ))

    return cursor.lastrowid

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




def solo_digitos(valor):
    """Devuelve solo los dígitos de una identificación."""
    return re.sub(r"\D", "", str(valor or ""))


def validar_cedula_ec(cedula):
    """Valida cédula ecuatoriana por estructura, provincia y dígito verificador."""
    cedula = solo_digitos(cedula)

    if len(cedula) != 10:
        return False

    if cedula == cedula[0] * 10:
        return False

    provincia = int(cedula[:2])
    tercer_digito = int(cedula[2])

    if provincia < 1 or provincia > 24:
        return False

    if tercer_digito >= 6:
        return False

    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0

    for i in range(9):
        producto = int(cedula[i]) * coeficientes[i]

        if producto >= 10:
            producto -= 9

        suma += producto

    digito_verificador = (10 - (suma % 10)) % 10

    return digito_verificador == int(cedula[9])


def calcular_modulo_11(numero, coeficientes):
    """Calcula dígito verificador módulo 11 para RUC público o privado."""
    suma = 0

    for digito, coeficiente in zip(numero, coeficientes):
        suma += int(digito) * coeficiente

    resultado = 11 - (suma % 11)

    if resultado == 11:
        return 0

    if resultado == 10:
        return None

    return resultado


def validar_ruc_ec(ruc):
    """Valida RUC ecuatoriano de persona natural, entidad pública o sociedad privada."""
    ruc = solo_digitos(ruc)

    if len(ruc) != 13:
        return False

    if ruc == ruc[0] * 13:
        return False

    provincia = int(ruc[:2])
    tercer_digito = int(ruc[2])

    if provincia < 1 or provincia > 24:
        return False

    # Los últimos 3 dígitos identifican el establecimiento.
    if ruc[-3:] == "000":
        return False

    # RUC persona natural: los primeros 10 dígitos deben ser cédula válida.
    if tercer_digito < 6:
        return validar_cedula_ec(ruc[:10])

    # RUC entidad pública: tercer dígito 6, verificador posición 9.
    if tercer_digito == 6:
        coeficientes = [3, 2, 7, 6, 5, 4, 3, 2]
        digito = calcular_modulo_11(ruc[:8], coeficientes)
        return digito is not None and digito == int(ruc[8])

    # RUC sociedad privada: tercer dígito 9, verificador posición 10.
    if tercer_digito == 9:
        coeficientes = [4, 3, 2, 7, 6, 5, 4, 3, 2]
        digito = calcular_modulo_11(ruc[:9], coeficientes)
        return digito is not None and digito == int(ruc[9])

    return False


def validar_identificacion_ec(valor):
    """Acepta cédula ecuatoriana de 10 dígitos o RUC de 13 dígitos."""
    identificacion = solo_digitos(valor)

    if len(identificacion) == 10:
        return validar_cedula_ec(identificacion)

    if len(identificacion) == 13:
        return validar_ruc_ec(identificacion)

    return False

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


TIPOS_ESTABLECIMIENTO = {
    "institucion": "Institución afiliada",
    "concesionario": "Concesionario",
    "centro_atencion": "Centro de atención",
}


def tipo_establecimiento_label(tipo):
    return TIPOS_ESTABLECIMIENTO.get(str(tipo or "").strip(), "Establecimiento")


def limpiar_servicios_establecimiento(servicios):
    """Devuelve una lista limpia desde texto separado por comas o JSON."""

    if not servicios:
        return []

    if isinstance(servicios, (list, tuple)):
        valores = servicios
    else:
        texto = str(servicios or "").strip()
        if not texto:
            return []
        try:
            valores = json.loads(texto)
            if not isinstance(valores, list):
                valores = [texto]
        except Exception:
            valores = re.split(r"[,;\n]+", texto)

    resultado = []
    for valor in valores:
        valor_limpio = str(valor or "").strip()
        if valor_limpio and valor_limpio not in resultado:
            resultado.append(valor_limpio[:80])
    return resultado


def serializar_servicios_establecimiento(servicios):
    return json.dumps(limpiar_servicios_establecimiento(servicios), ensure_ascii=False)


def enriquecer_establecimiento(fila):
    """Convierte sqlite.Row de establecimiento en dict listo para templates/JSON."""

    if not fila:
        return None

    item = dict(fila)
    item["tipo_label"] = tipo_establecimiento_label(item.get("tipo"))
    item["servicios_lista"] = limpiar_servicios_establecimiento(item.get("servicios"))
    item["activo"] = int(item.get("activo") if item.get("activo") is not None else 1)

    for campo in ("lat", "lng", "pin_x", "pin_y", "distancia_km"):
        try:
            item[campo] = float(item.get(campo)) if item.get(campo) not in (None, "") else None
        except (TypeError, ValueError):
            item[campo] = None

    if item.get("pin_x") is None:
        item["pin_x"] = 50.0
    if item.get("pin_y") is None:
        item["pin_y"] = 50.0

    item["pin_x"] = max(4.0, min(96.0, item["pin_x"]))
    item["pin_y"] = max(4.0, min(96.0, item["pin_y"]))
    return item


def listar_establecimientos(cursor, incluir_inactivos=False, solo_tipo=None):
    """Lista establecimientos. Si falta la tabla, devuelve lista vacía para no romper la app."""

    try:
        condiciones = []
        parametros = []

        if not incluir_inactivos:
            condiciones.append("COALESCE(activo, 1) = 1")

        if solo_tipo:
            condiciones.append("tipo = ?")
            parametros.append(solo_tipo)

        where = ""
        if condiciones:
            where = "WHERE " + " AND ".join(condiciones)

        cursor.execute(f"""
            SELECT *
            FROM establecimientos
            {where}
            ORDER BY
                COALESCE(activo, 1) DESC,
                CASE tipo
                    WHEN 'concesionario' THEN 1
                    WHEN 'institucion' THEN 2
                    WHEN 'centro_atencion' THEN 3
                    ELSE 4
                END,
                nombre COLLATE NOCASE ASC
        """, parametros)

        return [enriquecer_establecimiento(fila) for fila in cursor.fetchall()]
    except sqlite3.OperationalError as error:
        if "establecimientos" in str(error).lower():
            return []
        raise


def obtener_establecimiento_por_id(cursor, establecimiento_id, incluir_inactivos=True):
    try:
        if incluir_inactivos:
            cursor.execute("SELECT * FROM establecimientos WHERE id = ?", (establecimiento_id,))
        else:
            cursor.execute("SELECT * FROM establecimientos WHERE id = ? AND COALESCE(activo, 1) = 1", (establecimiento_id,))
        return enriquecer_establecimiento(cursor.fetchone())
    except sqlite3.OperationalError as error:
        if "establecimientos" in str(error).lower():
            return None
        raise


def establecimiento_activo_por_nombre(cursor, nombre):
    nombre = str(nombre or "").strip()
    if not nombre:
        return None

    try:
        cursor.execute("""
            SELECT *
            FROM establecimientos
            WHERE LOWER(nombre) = LOWER(?)
              AND COALESCE(activo, 1) = 1
            LIMIT 1
        """, (nombre,))
        return enriquecer_establecimiento(cursor.fetchone())
    except sqlite3.OperationalError as error:
        if "establecimientos" in str(error).lower():
            return None
        raise


def contar_establecimientos_por_tipo(establecimientos):
    conteos = {
        "total": 0,
        "institucion": 0,
        "concesionario": 0,
        "centro_atencion": 0,
    }
    for item in establecimientos or []:
        if int(item.get("activo", 1)) != 1:
            continue
        conteos["total"] += 1
        tipo = item.get("tipo")
        if tipo in conteos:
            conteos[tipo] += 1
    return conteos

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


def desactivar_codigos_pendientes_vehiculo(cursor, vehiculo_id):
    """Desactiva códigos no usados cuando una unidad sale de la operación visible."""

    cursor.execute("""
        UPDATE codigos_vehiculo
        SET activo = 0
        WHERE vehiculo_id = ?
          AND usado = 0
    """, (
        vehiculo_id,
    ))


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

    validar_archivo_imagen_real(archivo)

    extension = archivo.filename.rsplit(".", 1)[1].lower()
    slug_codigo = crear_slug(codigo_catalogo)
    nombre_archivo = secure_filename(f"{slug_codigo}.{extension}")

    ruta_absoluta = os.path.join(app.config["VEHICLE_IMAGE_FOLDER"], nombre_archivo)
    archivo.save(ruta_absoluta)

    return f"img/vehicles/{nombre_archivo}"


def guardar_modelo_3d_local(archivo, marca, modelo, anio):
    """Guarda modelos 3D subidos desde admin/trabajador en static/models/vehicles/."""

    if not archivo or not getattr(archivo, "filename", ""):
        return None

    if not extension_permitida(archivo.filename, EXTENSIONES_MODELO_3D):
        raise ValueError("Formato de modelo 3D no permitido. Usa archivos GLB o GLTF.")

    extension = archivo.filename.rsplit(".", 1)[1].lower()
    slug_base = crear_slug(f"{marca}-{modelo}-{anio}")
    nombre_archivo = secure_filename(
        f"{slug_base}-{int(time.time())}-{secrets.token_hex(4)}.{extension}"
    )

    carpeta_destino = app.config["VEHICLE_3D_FOLDER"]
    os.makedirs(carpeta_destino, exist_ok=True)

    ruta_absoluta = os.path.join(carpeta_destino, nombre_archivo)
    archivo.save(ruta_absoluta)

    return f"models/vehicles/{nombre_archivo}"


def normalizar_preview_sistemas_json(valor):
    """Valida y compacta el JSON editable del preview 3D por sistemas."""

    texto = str(valor or "").strip()

    if not texto:
        return ""

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        raise ValueError(f"El JSON de información técnica del preview no es válido: {error.msg}.")

    if not isinstance(datos, (dict, list)):
        raise ValueError("La información técnica del preview debe ser un objeto o una lista JSON.")

    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def generar_codigo_catalogo(cursor, marca, modelo, anio, vehiculo_id=None):
    """Genera una referencia pública única tipo VIN-GMC-CANYON-AT4X-2023."""

    texto = f"VIN-{marca}-{modelo}-{anio}".upper()
    reemplazos = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N",
        "Ü": "U"
    }

    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)

    base = re.sub(r"[^A-Z0-9]+", "-", texto).strip("-")
    base = base[:46].strip("-") or "VIN-VEHICULO"
    candidato = base
    contador = 2

    while True:
        if vehiculo_id:
            cursor.execute(
                "SELECT COUNT(*) FROM vehiculos WHERE UPPER(TRIM(codigo_catalogo)) = UPPER(TRIM(?)) AND id != ?",
                (candidato, vehiculo_id)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM vehiculos WHERE UPPER(TRIM(codigo_catalogo)) = UPPER(TRIM(?))",
                (candidato,)
            )

        if cursor.fetchone()[0] == 0:
            return candidato

        candidato = f"{base}-{contador:02d}"
        contador += 1


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
def proteger_rutas_por_rol():
    """Bloquea acceso directo por URL a paneles y acciones operativas.

    Esta capa es intencionalmente centralizada para que, aunque una ruta se
    mueva durante un refactor o falte un decorador individual, el backend siga
    validando permisos por prefijo/ruta sensible.
    """

    ruta = request.path or "/"

    def requiere_login(destino=None):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a esta sección.", "info")
            return redirect(url_for("login", next=destino or ruta))
        return None

    def rol_actual():
        return str(session.get("rol", "")).upper()

    # Perfil y acciones del usuario autenticado.
    if ruta == "/perfil" or ruta.startswith("/perfil/"):
        bloqueo = requiere_login()
        if bloqueo:
            return bloqueo

    # Panel administrativo: solo ADMIN.
    if ruta == "/admin" or ruta.startswith("/admin/"):
        bloqueo = requiere_login()
        if bloqueo:
            return bloqueo

        if rol_actual() != "ADMIN":
            flash("No tienes permisos para acceder al panel de administración.", "warning")
            return redirect(url_for("perfil"))

    # Panel operativo: ADMIN o TRABAJADOR.
    if ruta == "/trabajador" or ruta.startswith("/trabajador/"):
        bloqueo = requiere_login()
        if bloqueo:
            return bloqueo

        if rol_actual() not in {"ADMIN", "TRABAJADOR"}:
            flash("No tienes permisos para acceder al panel operativo.", "warning")
            return redirect(url_for("perfil"))

    # Rutas operativas que no empiezan por /admin o /trabajador porque se
    # comparten entre ambos paneles.
    rutas_personal_exactas = {
        "/vehiculos/guardar",
        "/facturas/guardar",
        "/mantenimientos/buscar-vehiculos",
        "/mantenimientos/registrar",
    }

    rutas_personal_prefijos = (
        "/mantenimientos/",
        "/catalog/vehiculos/",
    )

    requiere_personal = (
        ruta in rutas_personal_exactas
        or any(ruta.startswith(prefijo) for prefijo in rutas_personal_prefijos)
    )

    if requiere_personal:
        bloqueo = requiere_login()
        if bloqueo:
            return bloqueo

        if rol_actual() not in {"ADMIN", "TRABAJADOR"}:
            flash("No tienes permisos para realizar esta acción operativa.", "warning")
            return redirect(url_for("perfil"))

    return None


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


@app.after_request
def aplicar_cabeceras_seguridad(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# ================= RATE LIMIT LOGIN =================

def obtener_ip_cliente():
    if TRUST_PROXY_HEADERS:
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

