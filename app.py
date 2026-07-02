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
from email.message import EmailMessage
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

app.config["MANUALS_FOLDER"] = os.path.join(
    app.root_path,
    "static",
    "docs",
    "manuales"
)

app.config["INVOICE_FOLDER"] = os.path.join(
    app.root_path,
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

def conectar_db():
    conexion = sqlite3.connect("vinova.db")
    conexion.row_factory = sqlite3.Row
    return conexion


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

        cursor.execute("""
            UPDATE vehiculo_modelos
            SET
                tipo_vehiculo = COALESCE(NULLIF(TRIM(?), ''), tipo_vehiculo),
                combustible = COALESCE(NULLIF(TRIM(?), ''), combustible),
                transmision = COALESCE(NULLIF(TRIM(?), ''), transmision),
                modelo_3d = ?,
                modelo_3d_id = ?,
                modelo_3d_tipo = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (
            tipo_vehiculo,
            combustible,
            transmision,
            modelo_3d_final,
            modelo_3d_id_final,
            modelo_3d_tipo_final,
            ahora,
            modelo_id,
        ))

        return {
            "id": modelo_id,
            "modelo_3d": modelo_3d_final,
            "modelo_3d_id": modelo_3d_id_final,
            "modelo_3d_tipo": modelo_3d_tipo_final,
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
            creado_por,
            creado_en,
            actualizado_en,
            activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
        usuario_id,
        ahora,
        ahora,
    ))

    return {
        "id": cursor.lastrowid,
        "modelo_3d": modelo_3d,
        "modelo_3d_id": modelo_3d_id,
        "modelo_3d_tipo": modelo_3d_tipo,
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
            base_url=app.root_path
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
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    if tabla_existe(cursor, "vehiculos"):
        columnas_vehiculos = {
            "archivado": "INTEGER DEFAULT 0",
            "archivado_en": "TEXT",
            "archivado_por": "INTEGER",
            "motivo_archivado": "TEXT",
            "actualizado_en": "TEXT",
            "placa": "TEXT"
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
            "establecimiento": "TEXT",
            "cedula": "TEXT",
            "reset_token_hash": "TEXT",
            "reset_token_expira": "TEXT",
            "notificar_correo": "INTEGER DEFAULT 1",
            "notificar_mantenimientos": "INTEGER DEFAULT 1",
            "notificar_alertas": "INTEGER DEFAULT 1",
            "notificar_facturas": "INTEGER DEFAULT 1",
            "notificar_recordatorios": "INTEGER DEFAULT 0"
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
        CREATE TABLE IF NOT EXISTS mensajes_contacto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL,
            telefono TEXT,
            asunto TEXT,
            mensaje TEXT NOT NULL,
            ip TEXT,
            user_agent TEXT,
            estado TEXT DEFAULT 'Nuevo',
            creado_en TEXT
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturas_vehiculo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            vehiculo_id INTEGER NOT NULL,
            usuario_vehiculo_id INTEGER,
            numero_factura TEXT,
            descripcion TEXT,
            archivo TEXT,
            enlace TEXT,
            fecha_factura TEXT,
            monto REAL DEFAULT 0,
            establecimiento TEXT,
            subido_por INTEGER,
            creado_en TEXT,
            actualizado_en TEXT,
            activo INTEGER DEFAULT 1,
            anulado_por INTEGER,
            anulado_en TEXT,
            motivo_anulacion TEXT
        )
    """)

    if tabla_existe(cursor, "facturas_vehiculo"):
        columnas_facturas = {
            "usuario_vehiculo_id": "INTEGER",
            "numero_factura": "TEXT",
            "descripcion": "TEXT",
            "archivo": "TEXT",
            "enlace": "TEXT",
            "fecha_factura": "TEXT",
            "monto": "REAL DEFAULT 0",
            "establecimiento": "TEXT",
            "subido_por": "INTEGER",
            "creado_en": "TEXT",
            "actualizado_en": "TEXT",
            "activo": "INTEGER DEFAULT 1",
            "anulado_por": "INTEGER",
            "anulado_en": "TEXT",
            "motivo_anulacion": "TEXT"
        }

        for columna, definicion in columnas_facturas.items():
            agregar_columna_si_falta(cursor, "facturas_vehiculo", columna, definicion)

        cursor.execute("""
            UPDATE facturas_vehiculo
            SET activo = COALESCE(activo, 1),
                monto = COALESCE(monto, 0),
                creado_en = COALESCE(creado_en, CURRENT_TIMESTAMP)
        """)

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

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_facturas_usuario
        ON facturas_vehiculo(usuario_id, activo)
        """,
        "índice de facturas por usuario"
    )

    ejecutar_sql_seguro(
        cursor,
        """
        CREATE INDEX IF NOT EXISTS idx_facturas_vehiculo
        ON facturas_vehiculo(vehiculo_id, activo)
        """,
        "índice de facturas por vehículo"
    )



    # ================= MODELOS BASE / RECURSOS COMPARTIDOS =================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehiculo_modelos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            anio INTEGER NOT NULL,
            tipo_vehiculo TEXT,
            combustible TEXT,
            transmision TEXT,
            modelo_3d TEXT,
            modelo_3d_id TEXT,
            modelo_3d_tipo TEXT DEFAULT 'glb',
            creado_por INTEGER,
            creado_en TEXT,
            actualizado_en TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    if tabla_existe(cursor, "vehiculos"):
        agregar_columna_si_falta(cursor, "vehiculos", "modelo_base_id", "INTEGER")

        cursor.execute("""
            SELECT DISTINCT
                TRIM(marca) AS marca,
                TRIM(modelo) AS modelo,
                anio,
                COALESCE(tipo_vehiculo, '') AS tipo_vehiculo,
                COALESCE(combustible, '') AS combustible,
                COALESCE(transmision, '') AS transmision,
                COALESCE(modelo_3d, '') AS modelo_3d,
                COALESCE(modelo_3d_id, '') AS modelo_3d_id,
                COALESCE(modelo_3d_tipo, 'glb') AS modelo_3d_tipo,
                COALESCE(creado_por, NULL) AS creado_por
            FROM vehiculos
            WHERE TRIM(COALESCE(marca, '')) != ''
              AND TRIM(COALESCE(modelo, '')) != ''
              AND anio IS NOT NULL
        """)

        modelos_existentes = cursor.fetchall()
        ahora_modelo = fecha_actual()

        for modelo_base in modelos_existentes:
            cursor.execute("""
                SELECT id, modelo_3d, modelo_3d_id, modelo_3d_tipo
                FROM vehiculo_modelos
                WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
                  AND anio = ?
                LIMIT 1
            """, (modelo_base[0], modelo_base[1], modelo_base[2]))
            fila_modelo = cursor.fetchone()

            if fila_modelo:
                modelo_id = fila_modelo[0]
                cursor.execute("""
                    UPDATE vehiculo_modelos
                    SET
                        tipo_vehiculo = COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), ?),
                        combustible = COALESCE(NULLIF(TRIM(combustible), ''), ?),
                        transmision = COALESCE(NULLIF(TRIM(transmision), ''), ?),
                        modelo_3d = COALESCE(NULLIF(TRIM(modelo_3d), ''), ?),
                        modelo_3d_id = COALESCE(NULLIF(TRIM(modelo_3d_id), ''), ?),
                        modelo_3d_tipo = COALESCE(NULLIF(TRIM(modelo_3d_tipo), ''), ?),
                        actualizado_en = COALESCE(actualizado_en, ?)
                    WHERE id = ?
                """, (modelo_base[3], modelo_base[4], modelo_base[5], modelo_base[6], modelo_base[7], modelo_base[8], ahora_modelo, modelo_id))
            else:
                cursor.execute("""
                    INSERT INTO vehiculo_modelos (
                        marca, modelo, anio, tipo_vehiculo, combustible, transmision,
                        modelo_3d, modelo_3d_id, modelo_3d_tipo, creado_por, creado_en, actualizado_en, activo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (*modelo_base, ahora_modelo, ahora_modelo))
                modelo_id = cursor.lastrowid

            cursor.execute("""
                UPDATE vehiculos
                SET
                    modelo_base_id = ?,
                    modelo_3d = COALESCE(NULLIF(TRIM(modelo_3d), ''), (SELECT modelo_3d FROM vehiculo_modelos WHERE id = ?)),
                    modelo_3d_id = COALESCE(NULLIF(TRIM(modelo_3d_id), ''), (SELECT modelo_3d_id FROM vehiculo_modelos WHERE id = ?)),
                    modelo_3d_tipo = COALESCE(NULLIF(TRIM(modelo_3d_tipo), ''), (SELECT modelo_3d_tipo FROM vehiculo_modelos WHERE id = ?))
                WHERE LOWER(TRIM(marca)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(modelo)) = LOWER(TRIM(?))
                  AND anio = ?
                  AND (modelo_base_id IS NULL OR modelo_base_id = 0)
            """, (modelo_id, modelo_id, modelo_id, modelo_id, modelo_base[0], modelo_base[1], modelo_base[2]))

        ejecutar_sql_seguro(cursor, """
            CREATE INDEX IF NOT EXISTS idx_vehiculos_modelo_base
            ON vehiculos(modelo_base_id)
        """, "índice de vehículos por modelo base")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manuales_modelo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modelo_id INTEGER NOT NULL,
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

    if tabla_existe(cursor, "manuales_modelo"):
        columnas_manuales_modelo = {
            "modelo_id": "INTEGER",
            "titulo": "TEXT",
            "tipo_documento": "TEXT",
            "archivo": "TEXT",
            "enlace": "TEXT",
            "descripcion": "TEXT",
            "subido_por": "INTEGER",
            "creado_en": "TEXT",
            "activo": "INTEGER DEFAULT 1"
        }
        for columna, definicion in columnas_manuales_modelo.items():
            agregar_columna_si_falta(cursor, "manuales_modelo", columna, definicion)

    if tabla_existe(cursor, "manuales_vehiculo") and tabla_existe(cursor, "manuales_modelo"):
        cursor.execute("""
            SELECT
                manuales_vehiculo.*,
                vehiculos.modelo_base_id
            FROM manuales_vehiculo
            INNER JOIN vehiculos ON vehiculos.id = manuales_vehiculo.vehiculo_id
            WHERE vehiculos.modelo_base_id IS NOT NULL
        """)
        manuales_antiguos = cursor.fetchall()

        for manual in manuales_antiguos:
            cursor.execute("""
                SELECT id
                FROM manuales_modelo
                WHERE modelo_id = ?
                  AND LOWER(TRIM(titulo)) = LOWER(TRIM(?))
                  AND COALESCE(archivo, '') = COALESCE(?, '')
                  AND COALESCE(enlace, '') = COALESCE(?, '')
                LIMIT 1
            """, (manual["modelo_base_id"], manual["titulo"], manual["archivo"], manual["enlace"]))

            if cursor.fetchone():
                continue

            cursor.execute("""
                INSERT INTO manuales_modelo (
                    modelo_id, titulo, tipo_documento, archivo, enlace, descripcion, subido_por, creado_en, activo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manual["modelo_base_id"], manual["titulo"], manual["tipo_documento"], manual["archivo"],
                manual["enlace"], manual["descripcion"], manual["subido_por"], manual["creado_en"], manual["activo"]
            ))

    ejecutar_sql_seguro(cursor, """
        CREATE INDEX IF NOT EXISTS idx_manuales_modelo
        ON manuales_modelo(modelo_id, activo)
    """, "índice de manuales por modelo")

    # Facturas generadas por VINOVA
    if tabla_existe(cursor, "facturas_vehiculo"):
        columnas_facturas_generadas = {
            "mantenimiento_id": "INTEGER",
            "tipo_factura": "TEXT DEFAULT 'Manual'",
            "concepto": "TEXT",
            "subtotal": "REAL DEFAULT 0",
            "impuesto": "REAL DEFAULT 0",
            "total": "REAL DEFAULT 0",
            "hora_factura": "TEXT",
            "generado_por": "INTEGER",
            "archivo_pdf": "TEXT",
            "estado": "TEXT DEFAULT 'Generada'",
            "anulado": "INTEGER DEFAULT 0"
        }

        for columna, definicion in columnas_facturas_generadas.items():
            agregar_columna_si_falta(cursor, "facturas_vehiculo", columna, definicion)

        cursor.execute("""
            UPDATE facturas_vehiculo
            SET
                tipo_factura = COALESCE(NULLIF(TRIM(tipo_factura), ''), 'Manual'),
                concepto = COALESCE(NULLIF(TRIM(concepto), ''), descripcion, 'Factura VINOVA'),
                subtotal = COALESCE(NULLIF(subtotal, 0), monto, 0),
                total = COALESCE(NULLIF(total, 0), monto, subtotal, 0),
                generado_por = COALESCE(generado_por, subido_por),
                archivo_pdf = COALESCE(NULLIF(TRIM(archivo_pdf), ''), archivo),
                estado = COALESCE(NULLIF(TRIM(estado), ''), 'Generada'),
                anulado = COALESCE(anulado, CASE WHEN COALESCE(activo, 1) = 1 THEN 0 ELSE 1 END)
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
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.cedula,
            COALESCE(usuarios.activo, 1) AS activo,
            usuarios.creado_en,
            usuarios.actualizado_en,
            COUNT(usuarios_vehiculos.id) AS total_vehiculos
        FROM usuarios
        LEFT JOIN usuarios_vehiculos
            ON usuarios_vehiculos.usuario_id = usuarios.id
        WHERE usuarios.rol = 'USUARIO'
        GROUP BY usuarios.id
        ORDER BY usuarios.id DESC
        LIMIT 80
    """)
    clientes = cursor.fetchall()

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

    cursor.execute("""
        SELECT
            facturas_vehiculo.*,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            subidor.nombre AS subido_por_nombre,
            subidor.rol AS subido_por_rol,
            subidor.establecimiento AS subido_por_establecimiento
        FROM facturas_vehiculo
        INNER JOIN usuarios
            ON usuarios.id = facturas_vehiculo.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = facturas_vehiculo.vehiculo_id
        LEFT JOIN usuarios AS subidor
            ON subidor.id = facturas_vehiculo.subido_por
        WHERE COALESCE(facturas_vehiculo.activo, 1) = 1
        ORDER BY DATE(facturas_vehiculo.fecha_factura) DESC, facturas_vehiculo.id DESC
        LIMIT 120
    """)

    facturas = []
    for fila in cursor.fetchall():
        factura = dict(fila)
        factura["fecha_visible"] = formatear_fecha_visible(factura.get("fecha_factura"))
        factura["monto"] = normalizar_precio(factura.get("total")) or normalizar_precio(factura.get("monto")) or 0
        factura["establecimiento"] = factura.get("establecimiento") or factura.get("subido_por_establecimiento") or "VINOVA"
        facturas.append(factura)

    cursor.execute("""
        SELECT COUNT(*)
        FROM facturas_vehiculo
        WHERE COALESCE(activo, 1) = 1
    """)
    total_facturas = cursor.fetchone()[0]

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
        clientes=clientes,
        mantenimientos=mantenimientos,
        total_mantenimientos=total_mantenimientos,
        facturas=facturas,
        total_facturas=total_facturas,
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

        desactivar_codigos_pendientes_vehiculo(cursor, vehiculo_id)

        conexion.commit()
        flash("Vehículo archivado correctamente. Sus códigos pendientes quedaron desactivados.", "success")

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



@app.route("/trabajador/usuarios/crear", methods=["POST"])
@login_required
@personal_required
def trabajador_crear_usuario():

    asegurar_migraciones_admin()

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "").strip()
    cedula = solo_digitos(request.form.get("cedula", ""))

    destino = url_for("trabajador_panel") + "#trabajador-clientes"

    if not nombre or not correo or not password:
        flash("Nombre, correo y contraseña son obligatorios para crear el cliente.", "warning")
        return redirect(destino)

    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(destino)

    if cedula and not validar_identificacion_ec(cedula):
        flash("La cédula o RUC del cliente no es válida.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        if cedula:
            cursor.execute("""
                SELECT id, nombre, correo
                FROM usuarios
                WHERE cedula = ?
                LIMIT 1
            """, (cedula,))

            usuario_con_cedula = cursor.fetchone()

            if usuario_con_cedula:
                flash("Esta cédula/RUC ya pertenece a otro cliente.", "warning")
                return redirect(destino)

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
                establecimiento,
                cedula
            )
            VALUES (?, ?, ?, 'USUARIO', 1, ?, '', ?)
        """, (
            nombre,
            correo,
            password_hash,
            ahora,
            cedula
        ))

        conexion.commit()

        usuario_correo = {
            "nombre": nombre,
            "correo": correo,
            "notificar_correo": 1,
            "notificar_mantenimientos": 1,
            "notificar_alertas": 1,
            "notificar_facturas": 1
        }
        contenido_html = plantilla_correo(
            "Cuenta de cliente creada",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>El equipo de VINOVA creó una cuenta de cliente para ti.</p>
            <p>Por seguridad, la contraseña temporal debe ser entregada por el asesor que registró la cuenta.</p>
            """,
            "Ir a VINOVA",
            construir_url_absoluta("login")
        )
        enviar_correo_usuario(
            usuario_correo,
            "general",
            "VINOVA | Cuenta de cliente creada",
            "Tu cuenta de cliente VINOVA fue creada correctamente.",
            contenido_html
        )

        flash("Cliente creado correctamente.", "success")

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe una cuenta con ese correo.", "warning")

    except Exception as error:
        conexion.rollback()
        print("Error al crear cliente desde panel trabajador:", error)
        flash("No se pudo crear el cliente. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect(destino)


@app.route("/trabajador/usuarios/<int:usuario_id>/cedula", methods=["POST"])
@login_required
@personal_required
def trabajador_actualizar_cedula_usuario(usuario_id):
    """Permite al personal agregar o actualizar la cédula/RUC de un cliente existente."""

    asegurar_migraciones_admin()

    destino = url_for("trabajador_panel") + "#trabajador-clientes"
    cedula = solo_digitos(request.form.get("cedula", ""))

    if not cedula:
        flash("Ingresa la cédula o RUC del cliente.", "warning")
        return redirect(destino)

    if not validar_identificacion_ec(cedula):
        flash("La cédula o RUC del cliente no es válida.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, correo, rol, cedula
            FROM usuarios
            WHERE id = ?
        """, (usuario_id,))
        usuario = cursor.fetchone()

        if not usuario:
            flash("Cliente no encontrado.", "warning")
            return redirect(destino)

        if str(usuario["rol"]).upper() != "USUARIO":
            flash("Solo se puede actualizar la cédula/RUC de cuentas cliente.", "warning")
            return redirect(destino)

        cedula_actual = solo_digitos(usuario["cedula"])

        if cedula_actual == cedula:
            flash("La cédula/RUC ingresada ya está registrada en este cliente.", "info")
            return redirect(destino)

        cursor.execute("""
            SELECT id, nombre, correo
            FROM usuarios
            WHERE cedula = ?
              AND id != ?
            LIMIT 1
        """, (cedula, usuario_id))

        usuario_con_cedula = cursor.fetchone()

        if usuario_con_cedula:
            flash("Esta cédula/RUC ya pertenece a otro cliente.", "warning")
            return redirect(destino)

        cursor.execute("""
            UPDATE usuarios
            SET cedula = ?, actualizado_en = ?
            WHERE id = ?
        """, (
            cedula,
            fecha_actual(),
            usuario_id
        ))

        conexion.commit()
        flash(f"Cédula/RUC actualizada para {usuario['nombre']}.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar cédula/RUC desde panel trabajador:", error)
        flash("No se pudo actualizar la cédula/RUC del cliente.", "error")

    finally:
        conexion.close()

    return redirect(destino)

# ================= INICIO =================

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/contacto", methods=["POST"])
def contacto():

    asegurar_migraciones_admin()

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    telefono = request.form.get("telefono", "").strip()
    asunto = request.form.get("asunto", "").strip() or "Solicitud desde formulario de contacto"
    mensaje = request.form.get("mensaje", "").strip()

    destino = request.referrer or url_for("inicio") + "#contacto"

    if not nombre or not correo or not mensaje:
        flash("Completa nombre, correo y mensaje para enviar la solicitud.", "warning")
        return redirect(destino)

    if "@" not in correo:
        flash("Ingresa un correo válido para que podamos responderte.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            INSERT INTO mensajes_contacto (
                nombre, correo, telefono, asunto, mensaje, ip, user_agent, estado, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Nuevo', ?)
        """, (
            nombre,
            correo,
            telefono,
            asunto,
            mensaje,
            obtener_ip_cliente(),
            request.headers.get("User-Agent", ""),
            fecha_actual()
        ))
        conexion.commit()

        mensaje_html = html.escape(mensaje).replace(chr(10), '<br>')
        texto_admin = (
            "Nueva solicitud de contacto en VINOVA\n\n"
            f"Nombre: {nombre}\n"
            f"Correo: {correo}\n"
            f"Teléfono: {telefono or 'N/D'}\n"
            f"Asunto: {asunto}\n\n"
            f"Mensaje:\n{mensaje}"
        )
        html_admin = plantilla_correo(
            "Nueva solicitud de contacto",
            f"""
            <p><strong>Nombre:</strong> {html.escape(nombre)}</p>
            <p><strong>Correo:</strong> {html.escape(correo)}</p>
            <p><strong>Teléfono:</strong> {html.escape(telefono or 'N/D')}</p>
            <p><strong>Asunto:</strong> {html.escape(asunto)}</p>
            <p><strong>Mensaje:</strong></p>
            <p>{mensaje_html}</p>
            """
        )
        enviar_correo(CONTACT_EMAIL, f"VINOVA | Contacto: {asunto}", texto_admin, html_admin, reply_to=correo)

        texto_cliente = (
            f"Hola {nombre},\n\n"
            "Recibimos tu solicitud de contacto en VINOVA. Nuestro equipo revisará el mensaje y responderá lo antes posible.\n\n"
            f"Asunto: {asunto}\n"
        )
        html_cliente = plantilla_correo(
            "Solicitud recibida",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>Recibimos tu solicitud de contacto en VINOVA. Nuestro equipo revisará el mensaje y responderá lo antes posible.</p>
            <p><strong>Asunto:</strong> {html.escape(asunto)}</p>
            """
        )
        enviar_correo(correo, "VINOVA | Hemos recibido tu mensaje", texto_cliente, html_cliente)

        flash("Mensaje registrado correctamente. La estructura de correo quedó preparada para envío real cuando se configure SMTP.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar/enviar contacto:", error)
        flash("No se pudo enviar el mensaje de contacto. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect(url_for("inicio") + "#contacto")


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


@app.route("/recuperar", methods=["POST"])
def recuperar_password():

    correo = (
        request.form.get("correo", "")
        or request.form.get("email", "")
    ).strip().lower()

    if not correo or "@" not in correo:
        flash("Ingresa un correo válido para solicitar recuperación de contraseña.", "warning")
        return redirect(url_for("login"))

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, correo, activo
            FROM usuarios
            WHERE correo = ?
            LIMIT 1
        """, (correo,))
        usuario = cursor.fetchone()

        if usuario and usuario["activo"] == 1:
            token = secrets.token_urlsafe(40)
            token_hash = generar_hash_token(token)
            expira = (datetime.now() + timedelta(minutes=PASSWORD_RESET_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                UPDATE usuarios
                SET reset_token_hash = ?,
                    reset_token_expira = ?,
                    actualizado_en = ?
                WHERE id = ?
            """, (
                token_hash,
                expira,
                fecha_actual(),
                usuario["id"]
            ))
            conexion.commit()

            enlace = construir_url_absoluta("restablecer_password", token=token)
            texto = (
                f"Hola {usuario['nombre']},\n\n"
                f"Solicitamos el restablecimiento de contraseña de tu cuenta VINOVA. "
                f"Abre este enlace antes de {PASSWORD_RESET_MINUTES} minutos:\n{enlace}\n\n"
                "Si no solicitaste este cambio, ignora este mensaje."
            )
            contenido_html = plantilla_correo(
                "Recuperación de contraseña",
                f"""
                <p>Hola <strong>{html.escape(usuario['nombre'])}</strong>,</p>
                <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta VINOVA.</p>
                <p>El enlace estará disponible durante <strong>{PASSWORD_RESET_MINUTES} minutos</strong>.</p>
                <p>Si no solicitaste este cambio, puedes ignorar este mensaje.</p>
                """,
                "Restablecer contraseña",
                enlace
            )
            enviar_correo(usuario["correo"], "VINOVA | Recuperación de contraseña", texto, contenido_html)
        else:
            conexion.rollback()

    except Exception as error:
        conexion.rollback()
        print("Error al procesar recuperación de contraseña:", error)

    finally:
        conexion.close()

    flash("Si el correo pertenece a una cuenta activa, se generó la solicitud de recuperación. En modo simulado, revisa la consola para ver el enlace.", "info")
    return redirect(url_for("login"))


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer_password(token):

    token = str(token or "").strip()

    if not token:
        flash("Enlace de recuperación inválido.", "warning")
        return redirect(url_for("login"))

    asegurar_migraciones_admin()

    token_hash = generar_hash_token(token)
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id, nombre, correo, reset_token_expira, activo
        FROM usuarios
        WHERE reset_token_hash = ?
        LIMIT 1
    """, (token_hash,))
    usuario = cursor.fetchone()

    if not usuario or usuario["activo"] != 1:
        conexion.close()
        flash("El enlace de recuperación no es válido o ya fue utilizado.", "warning")
        return redirect(url_for("login"))

    try:
        expira = datetime.strptime(str(usuario["reset_token_expira"]), "%Y-%m-%d %H:%M:%S")
    except Exception:
        expira = datetime.min

    if expira < datetime.now():
        cursor.execute("""
            UPDATE usuarios
            SET reset_token_hash = NULL,
                reset_token_expira = NULL
            WHERE id = ?
        """, (usuario["id"],))
        conexion.commit()
        conexion.close()
        flash("El enlace de recuperación expiró. Solicita uno nuevo.", "warning")
        return redirect(url_for("login"))

    if request.method == "GET":
        conexion.close()
        return render_template("reset_password.html", token=token, usuario=usuario)

    nueva_password = request.form.get("password", "")
    confirmar_password = request.form.get("confirmar_password", "")

    if len(nueva_password) < 8:
        conexion.close()
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("restablecer_password", token=token))

    if nueva_password != confirmar_password:
        conexion.close()
        flash("Las contraseñas no coinciden.", "warning")
        return redirect(url_for("restablecer_password", token=token))

    try:
        cursor.execute("""
            UPDATE usuarios
            SET password = ?,
                reset_token_hash = NULL,
                reset_token_expira = NULL,
                actualizado_en = ?
            WHERE id = ?
        """, (
            generate_password_hash(nueva_password),
            fecha_actual(),
            usuario["id"]
        ))
        conexion.commit()

        contenido_html = plantilla_correo(
            "Contraseña actualizada",
            f"""
            <p>Hola <strong>{html.escape(usuario['nombre'])}</strong>,</p>
            <p>La contraseña de tu cuenta VINOVA fue actualizada correctamente.</p>
            <p>Si no realizaste este cambio, comunícate con administración inmediatamente.</p>
            """
        )
        enviar_correo(usuario["correo"], "VINOVA | Contraseña actualizada", "Tu contraseña de VINOVA fue actualizada correctamente.", contenido_html)

        flash("Contraseña actualizada correctamente. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))

    except Exception as error:
        conexion.rollback()
        print("Error al restablecer contraseña:", error)
        flash("No se pudo actualizar la contraseña. Intenta nuevamente.", "error")
        return redirect(url_for("restablecer_password", token=token))

    finally:
        conexion.close()


# ================= REGISTRO =================

@app.route("/register", methods=["POST"])
def register():

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")

    if not nombre or not correo or not password:
        flash("Nombre, correo y contraseña son obligatorios.", "warning")
        return redirect(url_for("login"))

    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("login"))

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            "SELECT id FROM usuarios WHERE correo = ?",
            (correo,)
        )

        if cursor.fetchone():
            flash("Este correo ya está registrado.", "warning")
            return redirect(url_for("login"))

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

        usuario_correo = {
            "nombre": nombre,
            "correo": correo,
            "notificar_correo": 1,
            "notificar_mantenimientos": 1,
            "notificar_alertas": 1,
            "notificar_facturas": 1
        }
        contenido_html = plantilla_correo(
            "Cuenta creada correctamente",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>Tu cuenta en VINOVA fue creada correctamente. Ya puedes iniciar sesión y registrar vehículos mediante códigos de activación.</p>
            """,
            "Iniciar sesión",
            construir_url_absoluta("login")
        )
        enviar_correo_usuario(
            usuario_correo,
            "general",
            "VINOVA | Cuenta creada",
            "Tu cuenta en VINOVA fue creada correctamente.",
            contenido_html
        )

        flash("Cuenta creada correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al registrar usuario público:", error)
        flash("No se pudo crear la cuenta. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect(url_for("login"))

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
            SELECT DISTINCT
                manuales_modelo.*,
                vehiculos.codigo_catalogo,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio
            FROM vehiculos
            INNER JOIN manuales_modelo
                ON manuales_modelo.modelo_id = vehiculos.modelo_base_id
            WHERE vehiculos.id IN ({placeholders})
              AND COALESCE(manuales_modelo.activo, 1) = 1
            ORDER BY vehiculos.marca, vehiculos.modelo, manuales_modelo.id DESC
        """, ids_vehiculos)

        for fila in cursor.fetchall():
            manual = dict(fila)
            manual["creado_visible"] = formatear_fecha_visible(manual.get("creado_en"))
            manuales_usuario.append(manual)

    facturas_usuario = []

    cursor.execute("""
        SELECT
            facturas_vehiculo.*,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            subidor.nombre AS subido_por_nombre,
            subidor.rol AS subido_por_rol,
            subidor.establecimiento AS subido_por_establecimiento
        FROM facturas_vehiculo
        INNER JOIN vehiculos
            ON vehiculos.id = facturas_vehiculo.vehiculo_id
        LEFT JOIN usuarios AS subidor
            ON subidor.id = facturas_vehiculo.subido_por
        WHERE facturas_vehiculo.usuario_id = ?
          AND COALESCE(facturas_vehiculo.activo, 1) = 1
        ORDER BY DATE(facturas_vehiculo.fecha_factura) DESC, facturas_vehiculo.id DESC
    """, (
        session["usuario_id"],
    ))

    for fila in cursor.fetchall():
        factura = dict(fila)
        factura["fecha_visible"] = formatear_fecha_visible(factura.get("fecha_factura"))
        factura["monto"] = normalizar_precio(factura.get("total")) or normalizar_precio(factura.get("monto")) or 0
        factura["establecimiento"] = factura.get("establecimiento") or factura.get("subido_por_establecimiento") or "VINOVA"
        factura["monto"] = normalizar_precio(factura.get("total")) or normalizar_precio(factura.get("monto")) or 0
        facturas_usuario.append(factura)

    cursor.execute("""
        SELECT
            COALESCE(notificar_correo, 1) AS notificar_correo,
            COALESCE(notificar_mantenimientos, 1) AS notificar_mantenimientos,
            COALESCE(notificar_alertas, 1) AS notificar_alertas,
            COALESCE(notificar_facturas, 1) AS notificar_facturas,
            COALESCE(notificar_recordatorios, 0) AS notificar_recordatorios
        FROM usuarios
        WHERE id = ?
    """, (session["usuario_id"],))
    preferencias_notificacion = dict(cursor.fetchone() or {})

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
        manuales_usuario=manuales_usuario,
        facturas_usuario=facturas_usuario,
        preferencias_notificacion=preferencias_notificacion
    )


@app.route("/perfil/notificaciones", methods=["POST"])
@login_required
def actualizar_preferencias_notificacion():

    asegurar_migraciones_admin()

    notificar_correo = 1 if request.form.get("notificar_correo") == "1" else 0
    notificar_mantenimientos = 1 if request.form.get("notificar_mantenimientos") == "1" else 0
    notificar_alertas = 1 if request.form.get("notificar_alertas") == "1" else 0
    notificar_facturas = 1 if request.form.get("notificar_facturas") == "1" else 0
    notificar_recordatorios = 1 if request.form.get("notificar_recordatorios") == "1" else 0

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            UPDATE usuarios
            SET notificar_correo = ?,
                notificar_mantenimientos = ?,
                notificar_alertas = ?,
                notificar_facturas = ?,
                notificar_recordatorios = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (
            notificar_correo,
            notificar_mantenimientos,
            notificar_alertas,
            notificar_facturas,
            notificar_recordatorios,
            fecha_actual(),
            session["usuario_id"]
        ))
        conexion.commit()
        flash("Preferencias de notificación actualizadas correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar preferencias de notificación:", error)
        flash("No se pudieron guardar las preferencias de notificación.", "error")

    finally:
        conexion.close()

    return redirect("/perfil#seccion-notificaciones")


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
            usuarios.cedula AS usuario_cedula,
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
            "usuario_cedula": fila["usuario_cedula"] or "",
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
    cliente_cedula_form = solo_digitos(request.form.get("cliente_cedula", ""))
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
                usuarios.correo AS usuario_correo,
                usuarios.cedula AS usuario_cedula,
                COALESCE(usuarios.notificar_correo, 1) AS notificar_correo,
                COALESCE(usuarios.notificar_mantenimientos, 1) AS notificar_mantenimientos,
                COALESCE(usuarios.notificar_alertas, 1) AS notificar_alertas,
                COALESCE(usuarios.notificar_facturas, 1) AS notificar_facturas,
                vehiculos.codigo_catalogo,
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

        cedula_actual = solo_digitos(registro["usuario_cedula"])
        cedula_factura = cliente_cedula_form or cedula_actual

        if not cedula_factura:
            flash("Ingresa la cédula o RUC del cliente para emitir la factura.", "warning")
            return redirect(destino)

        if not validar_identificacion_ec(cedula_factura):
            flash("La cédula o RUC del cliente no es válida.", "warning")
            return redirect(destino)

        if cedula_factura != cedula_actual:
            cursor.execute("""
                UPDATE usuarios
                SET cedula = ?, actualizado_en = ?
                WHERE id = ?
            """, (
                cedula_factura,
                fecha_actual(),
                registro["usuario_id"]
            ))

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

        mantenimiento_id = cursor.lastrowid

        registro_factura = dict(registro)
        registro_factura["codigo_catalogo"] = registro_factura.get("codigo_catalogo") or ""
        registro_factura["kilometraje_actual"] = kilometraje_actual
        registro_factura["establecimiento"] = establecimiento
        registro_factura["usuario_cedula"] = cedula_factura
        registro_factura["cedula"] = cedula_factura

        factura_id = registrar_factura_generada(
            cursor,
            registro=registro_factura,
            tipo_factura="Mantenimiento",
            concepto=f"Mantenimiento - {tipo_servicio}",
            descripcion=descripcion or observaciones or f"Servicio de {tipo_servicio}",
            subtotal=costo or 0,
            impuesto=0,
            descuento=0,
            mantenimiento_id=mantenimiento_id,
            items=[
                {
                    "descripcion": descripcion or observaciones or f"Servicio de {tipo_servicio}",
                    "cantidad": 1,
                    "precio_unitario": costo or 0,
                    "total": costo or 0
                }
            ],
            observaciones=observaciones,
            fecha_factura=fecha_servicio
        )

        if not factura_id:
            raise RuntimeError("No se pudo crear la factura del mantenimiento.")

        conexion.commit()

        usuario_correo = {
            "nombre": registro["usuario_nombre"],
            "correo": registro["usuario_correo"],
            "notificar_correo": registro["notificar_correo"],
            "notificar_mantenimientos": registro["notificar_mantenimientos"],
            "notificar_alertas": registro["notificar_alertas"],
            "notificar_facturas": registro["notificar_facturas"]
        }
        vehiculo_texto = f"{registro['marca']} {registro['modelo']} {registro['anio']}"
        proxima_fecha_visible = formatear_fecha_visible(calculo["proxima_fecha"]) if calculo.get("proxima_fecha") else "N/D"
        proximo_km_visible = (f"{calculo['proximo_kilometraje']:,} km".replace(",", ".") if calculo.get("proximo_kilometraje") is not None else "N/D")
        km_actual_visible = f"{kilometraje_actual:,} km".replace(",", ".")
        contenido_html = plantilla_correo(
            "Mantenimiento registrado",
            f"""
            <p>Hola <strong>{html.escape(registro['usuario_nombre'])}</strong>,</p>
            <p>VINOVA registró un mantenimiento para tu vehículo <strong>{html.escape(vehiculo_texto)}</strong>.</p>
            <ul>
                <li><strong>Servicio:</strong> {html.escape(tipo_servicio)}</li>
                <li><strong>Fecha:</strong> {html.escape(formatear_fecha_visible(fecha_servicio))}</li>
                <li><strong>Kilometraje:</strong> {html.escape(km_actual_visible)}</li>
                <li><strong>Próxima fecha sugerida:</strong> {html.escape(proxima_fecha_visible)}</li>
                <li><strong>Próximo kilometraje sugerido:</strong> {html.escape(proximo_km_visible)}</li>
            </ul>
            <p>La factura generada ya está disponible en tu perfil.</p>
            """,
            "Ver mi perfil",
            construir_url_absoluta("perfil")
        )
        enviar_correo_usuario(
            usuario_correo,
            "mantenimiento",
            "VINOVA | Mantenimiento registrado",
            f"VINOVA registró un mantenimiento para tu vehículo {vehiculo_texto}.",
            contenido_html
        )

        flash("Mantenimiento registrado correctamente. La factura ya está visible en el perfil del cliente.", "success")

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
                COALESCE(vehiculos.archivado, 0) AS vehiculo_archivado,
                usuarios.nombre AS usuario_nombre,
                usuarios.correo AS usuario_correo,
                COALESCE(usuarios.notificar_correo, 1) AS notificar_correo,
                COALESCE(usuarios.notificar_mantenimientos, 1) AS notificar_mantenimientos,
                COALESCE(usuarios.notificar_alertas, 1) AS notificar_alertas,
                COALESCE(usuarios.notificar_facturas, 1) AS notificar_facturas
            FROM codigos_vehiculo
            INNER JOIN vehiculos
                ON vehiculos.id = codigos_vehiculo.vehiculo_id
            INNER JOIN usuarios
                ON usuarios.id = ?
            WHERE codigos_vehiculo.codigo = ?
            LIMIT 1
        """, (
            session["usuario_id"],
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

        usuario_correo = {
            "nombre": codigo["usuario_nombre"],
            "correo": codigo["usuario_correo"],
            "notificar_correo": codigo["notificar_correo"],
            "notificar_mantenimientos": codigo["notificar_mantenimientos"],
            "notificar_alertas": codigo["notificar_alertas"],
            "notificar_facturas": codigo["notificar_facturas"]
        }
        vehiculo_texto = f"{codigo['marca']} {codigo['modelo']} {codigo['anio']}"
        contenido_html = plantilla_correo(
            "Vehículo registrado en tu perfil",
            f"""
            <p>Hola <strong>{html.escape(codigo['usuario_nombre'])}</strong>,</p>
            <p>El vehículo <strong>{html.escape(vehiculo_texto)}</strong> fue registrado correctamente en tu perfil VINOVA.</p>
            <p>Desde tu panel podrás consultar historial de servicios, próximos mantenimientos, manuales y facturas asociadas.</p>
            """,
            "Ir a mi perfil",
            construir_url_absoluta("perfil")
        )
        enviar_correo_usuario(
            usuario_correo,
            "general",
            "VINOVA | Vehículo registrado",
            f"El vehículo {vehiculo_texto} fue registrado correctamente en tu perfil VINOVA.",
            contenido_html
        )

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
            manuales_modelo.*,
            vehiculo_modelos.marca,
            vehiculo_modelos.modelo,
            vehiculo_modelos.anio,
            usuarios.nombre AS subido_por_nombre
        FROM manuales_modelo
        INNER JOIN vehiculo_modelos
            ON vehiculo_modelos.id = manuales_modelo.modelo_id
        LEFT JOIN usuarios
            ON usuarios.id = manuales_modelo.subido_por
        ORDER BY manuales_modelo.id DESC
    """)
    manuales_admin = cursor.fetchall()

    cursor.execute("""
        SELECT
            facturas_vehiculo.*,
            usuarios.nombre AS usuario_nombre,
            usuarios.correo AS usuario_correo,
            vehiculos.codigo_catalogo,
            vehiculos.marca,
            vehiculos.modelo,
            vehiculos.anio,
            subidor.nombre AS subido_por_nombre,
            subidor.rol AS subido_por_rol,
            subidor.establecimiento AS subido_por_establecimiento
        FROM facturas_vehiculo
        INNER JOIN usuarios
            ON usuarios.id = facturas_vehiculo.usuario_id
        INNER JOIN vehiculos
            ON vehiculos.id = facturas_vehiculo.vehiculo_id
        LEFT JOIN usuarios AS subidor
            ON subidor.id = facturas_vehiculo.subido_por
        ORDER BY facturas_vehiculo.id DESC
    """)

    facturas_admin = []
    for fila in cursor.fetchall():
        factura = dict(fila)
        factura["fecha_visible"] = formatear_fecha_visible(factura.get("fecha_factura"))
        factura["monto"] = normalizar_precio(factura.get("total")) or normalizar_precio(factura.get("monto")) or 0
        factura["establecimiento"] = factura.get("establecimiento") or factura.get("subido_por_establecimiento") or "VINOVA"
        facturas_admin.append(factura)

    cursor.execute("""
        SELECT COUNT(*)
        FROM facturas_vehiculo
        WHERE COALESCE(activo, 1) = 1
    """)
    total_facturas = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.cedula,
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
        manuales_admin=manuales_admin,
        facturas_admin=facturas_admin,
        total_facturas=total_facturas
    )


@app.route("/admin/vehiculos/guardar", methods=["POST"])
@app.route("/vehiculos/guardar", methods=["POST"])
@login_required
@personal_required
def admin_guardar_vehiculo():

    asegurar_migraciones_admin()

    origen = request.form.get("origen", "admin").strip().lower()
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
        return redirigir_operativo("vehiculos", origen)

    try:
        anio = int(anio)
        kilometraje = normalizar_kilometraje(kilometraje)
        precio = normalizar_precio(precio)
    except ValueError:
        flash("Año, kilometraje y precio deben ser valores numéricos.", "warning")
        return redirigir_operativo("vehiculos", origen)

    if kilometraje is None:
        flash("El kilometraje debe ser un valor numérico válido.", "warning")
        return redirigir_operativo("vehiculos", origen)

    if precio is None:
        flash("El precio debe ser un valor numérico válido.", "warning")
        return redirigir_operativo("vehiculos", origen)

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
                return redirigir_operativo("vehiculos", origen)

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
                    return redirigir_operativo("ventas", origen)

                estado = "Vendido"
                activo = 0

            referencia_bloqueada = (
                vehiculo_tiene_codigo
                or vehiculo_tiene_registro_usuario
            )

            if referencia_bloqueada and codigo_catalogo != vehiculo_actual["codigo_catalogo"]:
                flash("No puedes cambiar el código de catálogo de un vehículo que ya tiene código, venta o registro.", "warning")
                return redirigir_operativo("vehiculos", origen)

        modelo_base = obtener_o_crear_modelo_base(
            cursor,
            marca,
            modelo,
            anio,
            tipo_vehiculo,
            combustible,
            transmision,
            modelo_3d,
            modelo_3d_id,
            modelo_3d_tipo,
            session.get("usuario_id")
        )
        modelo_base_id = modelo_base["id"]
        modelo_3d = modelo_base.get("modelo_3d", "")
        modelo_3d_id = modelo_base.get("modelo_3d_id", "")
        modelo_3d_tipo = modelo_base.get("modelo_3d_tipo", modelo_3d_tipo)

        try:
            imagen_guardada = guardar_imagen_vehiculo(archivo_imagen, codigo_catalogo)
        except ValueError as error:
            flash(str(error), "warning")
            return redirigir_operativo("vehiculos", origen)

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
                        modelo_base_id = ?,
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
                    modelo_base_id,
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
                        modelo_base_id = ?,
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
                    modelo_base_id,
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
                    modelo_base_id,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                modelo_base_id,
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

        guardar_manual_modelo_desde_form(cursor, modelo_base_id, session.get("usuario_id"))

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

    return redirigir_operativo("vehiculos", origen)


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

        desactivar_codigos_pendientes_vehiculo(cursor, vehiculo_id)

        conexion.commit()
        flash("Vehículo archivado correctamente. Se conservará en el historial interno y sus códigos pendientes quedaron desactivados.", "success")

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

        nuevo_activo = 0 if canje["vehiculo_archivado"] == 1 else 1
        nuevo_codigo_activo = nuevo_activo

        if canje["codigo_vehiculo_id"]:
            cursor.execute("""
                UPDATE codigos_vehiculo
                SET
                    usado = 0,
                    usado_por = NULL,
                    fecha_uso = NULL,
                    activo = ?
                WHERE id = ?
            """, (
                nuevo_codigo_activo,
                canje["codigo_vehiculo_id"],
            ))


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
    cedula = solo_digitos(request.form.get("cedula", ""))

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

    if cedula and not validar_identificacion_ec(cedula):
        flash("La cédula o RUC ingresado no es válido.", "warning")
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
                establecimiento,
                cedula
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombre,
            correo,
            password_hash,
            rol,
            1,
            ahora,
            establecimiento if rol == "TRABAJADOR" else "",
            cedula
        ))

        conexion.commit()

        usuario_correo = {
            "nombre": nombre,
            "correo": correo,
            "notificar_correo": 1,
            "notificar_mantenimientos": 1,
            "notificar_alertas": 1,
            "notificar_facturas": 1
        }
        contenido_html = plantilla_correo(
            "Cuenta creada por administración",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>Administración creó una cuenta VINOVA con rol <strong>{html.escape(rol)}</strong>.</p>
            <p>Por seguridad, la contraseña temporal debe ser entregada por el responsable que creó la cuenta.</p>
            """,
            "Iniciar sesión",
            construir_url_absoluta("login")
        )
        enviar_correo_usuario(
            usuario_correo,
            "general",
            "VINOVA | Cuenta creada",
            "Administración creó una cuenta VINOVA para ti.",
            contenido_html
        )

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
@personal_required
def admin_guardar_manual_vehiculo():

    asegurar_migraciones_admin()

    origen = request.form.get("origen", "admin").strip().lower()
    modelo_id = request.form.get("modelo_id", type=int)
    marca = request.form.get("marca", "").strip()
    modelo = request.form.get("modelo", "").strip()
    anio = request.form.get("anio", type=int)

    if not modelo_id:
        if not marca or not modelo or not anio:
            flash("Selecciona un modelo o indica marca, modelo y año.", "warning")
            return redirigir_operativo("manuales", origen)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        if not modelo_id:
            modelo_base = obtener_o_crear_modelo_base(cursor, marca, modelo, anio, usuario_id=session.get("usuario_id"))
            modelo_id = modelo_base["id"]

        guardar_manual_modelo_desde_form(cursor, modelo_id, session.get("usuario_id"))
        conexion.commit()
        flash("Manual guardado para el modelo. Todas las unidades iguales lo usarán automáticamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar manual por modelo:", error)
        flash("No se pudo guardar el manual.", "error")

    finally:
        conexion.close()

    return redirigir_operativo("manuales", origen)


@app.route("/admin/manuales/<int:manual_id>/estado", methods=["POST"])
@login_required
@personal_required
def admin_cambiar_estado_manual(manual_id):

    asegurar_migraciones_admin()
    origen = request.form.get("origen", "admin").strip().lower()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, COALESCE(activo, 1) AS activo
            FROM manuales_modelo
            WHERE id = ?
        """, (manual_id,))
        manual = cursor.fetchone()

        if not manual:
            flash("Manual no encontrado.", "warning")
            return redirigir_operativo("manuales", origen)

        nuevo_estado = 0 if manual["activo"] == 1 else 1
        cursor.execute("UPDATE manuales_modelo SET activo = ? WHERE id = ?", (nuevo_estado, manual_id))
        conexion.commit()
        flash("Manual activado." if nuevo_estado == 1 else "Manual ocultado.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar manual:", error)
        flash("No se pudo actualizar el manual.", "error")

    finally:
        conexion.close()

    return redirigir_operativo("manuales", origen)


# ================= FACTURAS DE VEHÍCULOS =================

@app.route("/facturas/guardar", methods=["POST"])
@login_required
@personal_required
def guardar_factura_vehiculo():

    asegurar_migraciones_admin()

    descuento = normalizar_precio(request.form.get("descuento")) or 0
    observaciones = request.form.get("observaciones", "").strip()
    origen = request.form.get("origen", "trabajador").strip().lower()
    destino = "/admin/vehiculos#admin-facturas" if origen == "admin" else "/trabajador#trabajador-facturas"

    usuario_vehiculo_id = request.form.get("usuario_vehiculo_id", type=int)
    numero_factura = request.form.get("numero_factura", "").strip().upper()
    fecha_factura = normalizar_fecha(request.form.get("fecha_factura")) or datetime.now().strftime("%Y-%m-%d")
    tipo_factura = request.form.get("tipo_factura", "Producto").strip() or "Producto"
    concepto = request.form.get("concepto", "").strip() or request.form.get("descripcion", "").strip() or "Factura manual VINOVA"
    descripcion = request.form.get("descripcion", "").strip() or concepto
    subtotal = normalizar_precio(request.form.get("monto")) or normalizar_precio(request.form.get("subtotal")) or 0
    impuesto = normalizar_precio(request.form.get("impuesto")) or 0
    cliente_cedula_form = solo_digitos(request.form.get("cliente_cedula", ""))

    if not usuario_vehiculo_id:
        flash("Selecciona el cliente y vehículo al que pertenece la factura.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT
                usuarios_vehiculos.id AS usuario_vehiculo_id,
                usuarios_vehiculos.usuario_id,
                usuarios_vehiculos.vehiculo_id,
                usuarios_vehiculos.kilometraje_inicial AS kilometraje_referencia,
                usuarios.nombre AS usuario_nombre,
                usuarios.correo AS usuario_correo,
                usuarios.cedula AS usuario_cedula,
                COALESCE(usuarios.notificar_correo, 1) AS notificar_correo,
                COALESCE(usuarios.notificar_mantenimientos, 1) AS notificar_mantenimientos,
                COALESCE(usuarios.notificar_alertas, 1) AS notificar_alertas,
                COALESCE(usuarios.notificar_facturas, 1) AS notificar_facturas,
                vehiculos.codigo_catalogo,
                vehiculos.marca,
                vehiculos.modelo,
                vehiculos.anio
            FROM usuarios_vehiculos
            INNER JOIN usuarios
                ON usuarios.id = usuarios_vehiculos.usuario_id
            INNER JOIN vehiculos
                ON vehiculos.id = usuarios_vehiculos.vehiculo_id
            WHERE usuarios_vehiculos.id = ?
        """, (usuario_vehiculo_id,))

        registro = cursor.fetchone()

        if not registro:
            flash("No encontré ese vehículo registrado en un perfil de cliente.", "warning")
            return redirect(destino)

        cedula_actual = solo_digitos(registro["usuario_cedula"])
        cedula_factura = cliente_cedula_form or cedula_actual

        if not cedula_factura:
            flash("Ingresa la cédula o RUC del cliente para emitir la factura.", "warning")
            return redirect(destino)

        if not validar_identificacion_ec(cedula_factura):
            flash("La cédula o RUC del cliente no es válida.", "warning")
            return redirect(destino)

        if cedula_factura != cedula_actual:
            cursor.execute("""
                UPDATE usuarios
                SET cedula = ?, actualizado_en = ?
                WHERE id = ?
            """, (
                cedula_factura,
                fecha_actual(),
                registro["usuario_id"]
            ))

        registro_factura = dict(registro)
        registro_factura["usuario_cedula"] = cedula_factura
        registro_factura["cedula"] = cedula_factura

        registrar_factura_generada(
            cursor,
            registro=registro_factura,
            tipo_factura=tipo_factura,
            concepto=concepto,
            descripcion=descripcion,
            subtotal=subtotal,
            impuesto=impuesto,
            descuento=descuento,
            mantenimiento_id=None,
            numero_factura=numero_factura,
            fecha_factura=fecha_factura,
            observaciones=observaciones
        )

        conexion.commit()

        usuario_correo = {
            "nombre": registro["usuario_nombre"],
            "correo": registro["usuario_correo"],
            "notificar_correo": registro["notificar_correo"],
            "notificar_mantenimientos": registro["notificar_mantenimientos"],
            "notificar_alertas": registro["notificar_alertas"],
            "notificar_facturas": registro["notificar_facturas"]
        }
        vehiculo_texto = f"{registro['marca']} {registro['modelo']} {registro['anio']}"
        total_estimado = max(0, subtotal + impuesto - descuento)
        contenido_html = plantilla_correo(
            "Factura disponible",
            f"""
            <p>Hola <strong>{html.escape(registro['usuario_nombre'])}</strong>,</p>
            <p>VINOVA generó una factura asociada a tu vehículo <strong>{html.escape(vehiculo_texto)}</strong>.</p>
            <ul>
                <li><strong>Tipo:</strong> {html.escape(tipo_factura)}</li>
                <li><strong>Concepto:</strong> {html.escape(concepto)}</li>
                <li><strong>Fecha:</strong> {html.escape(formatear_fecha_visible(fecha_factura))}</li>
                <li><strong>Total:</strong> ${total_estimado:,.2f}</li>
            </ul>
            <p>Puedes revisar el documento desde la sección Facturas de tu perfil.</p>
            """,
            "Ver facturas",
            construir_url_absoluta("perfil") + "#seccion-facturas"
        )
        enviar_correo_usuario(
            usuario_correo,
            "factura",
            "VINOVA | Factura disponible",
            f"VINOVA generó una factura para tu vehículo {vehiculo_texto}.",
            contenido_html
        )

        flash("Factura PDF generada correctamente y visible en el perfil del cliente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al generar factura:", error)
        flash("No se pudo generar la factura.", "error")

    finally:
        conexion.close()

    return redirect(destino)


@app.route("/admin/facturas/<int:factura_id>/estado", methods=["POST"])
@login_required
@admin_required
def admin_cambiar_estado_factura(factura_id):

    asegurar_migraciones_admin()

    motivo = request.form.get("motivo_anulacion", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, COALESCE(activo, 1) AS activo
            FROM facturas_vehiculo
            WHERE id = ?
        """, (
            factura_id,
        ))

        factura = cursor.fetchone()

        if not factura:
            flash("Factura no encontrada.", "warning")
            return redirigir_admin("facturas")

        nuevo_estado = 0 if factura["activo"] == 1 else 1
        ahora = fecha_actual()

        if nuevo_estado == 0:
            cursor.execute("""
                UPDATE facturas_vehiculo
                SET activo = 0,
                    anulado_por = ?,
                    anulado_en = ?,
                    motivo_anulacion = ?,
                    actualizado_en = ?
                WHERE id = ?
            """, (
                session.get("usuario_id"),
                ahora,
                motivo or "Ocultada desde administración",
                ahora,
                factura_id
            ))
        else:
            cursor.execute("""
                UPDATE facturas_vehiculo
                SET activo = 1,
                    anulado_por = NULL,
                    anulado_en = NULL,
                    motivo_anulacion = NULL,
                    actualizado_en = ?
                WHERE id = ?
            """, (
                ahora,
                factura_id
            ))

        conexion.commit()
        flash("Factura activada correctamente." if nuevo_estado == 1 else "Factura ocultada correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar estado de factura:", error)
        flash("No se pudo actualizar la factura.", "error")

    finally:
        conexion.close()

    return redirigir_admin("facturas")


@app.route("/facturas/<int:factura_id>/ver")
@login_required
def ver_factura_vehiculo(factura_id):

    asegurar_migraciones_admin()

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM facturas_vehiculo
        WHERE id = ?
    """, (
        factura_id,
    ))

    factura = cursor.fetchone()
    conexion.close()

    if not factura:
        abort(404)

    rol = str(session.get("rol", "")).upper()
    es_personal = rol in {"ADMIN", "TRABAJADOR"}

    if not es_personal and factura["usuario_id"] != session.get("usuario_id"):
        abort(403)

    if not es_personal and factura["activo"] != 1:
        abort(404)

    if factura["enlace"]:
        return redirect(factura["enlace"])

    archivo = normalizar_ruta_static_documento(factura["archivo_pdf"] or factura["archivo"])

    if not archivo:
        flash("La factura no tiene archivo disponible.", "warning")
        return redirect(url_for("perfil") + "#seccion-facturas")

    return send_from_directory(app.static_folder, archivo, as_attachment=False)


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