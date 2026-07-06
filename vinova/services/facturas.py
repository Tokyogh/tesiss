from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from flask import abort, redirect, send_file, send_from_directory, session, url_for, flash

from vinova.services.storage import (
    factura_privada_existe,
    normalizar_ruta_factura_privada,
    normalizar_ruta_factura_static_legacy,
    preparar_destino_factura_privada,
    ruta_absoluta_factura_privada,
)


def _pdf_escape(valor):
    texto = str(valor or "")
    texto = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    texto = texto.replace("\r", " ").replace("\n", " ")
    return texto


def _pdf_text(x, y, texto, size=10, bold=False):
    font = "F2" if bold else "F1"
    return f"BT /{font} {size} Tf {x} {y} Td ({_pdf_escape(texto)}) Tj ET"


def generar_pdf_factura(datos):
    """Genera una factura PDF VINOVA en almacenamiento privado."""

    from vinova.core import (
        BASE_DIR,
        app,
        crear_slug,
        generar_numero_factura,
        normalizar_precio,
        render_template,
    )

    numero_factura = (
        str(datos.get("numero_factura") or "").strip().upper()
        or generar_numero_factura(datos.get("usuario_vehiculo_id"))
    )

    nombre_archivo = f"{crear_slug(numero_factura)}.pdf"
    ruta_relativa_privada, ruta_pdf = preparar_destino_factura_privada(nombre_archivo)

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
                "total": subtotal,
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
        "total": total,
    }

    cliente = {
        "nombre": datos.get("cliente_nombre") or datos.get("usuario_nombre") or "Cliente VINOVA",
        "correo": datos.get("cliente_correo") or datos.get("usuario_correo") or "N/D",
        "cedula": datos.get("cliente_cedula") or datos.get("usuario_cedula") or datos.get("cedula") or "N/D",
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
        ),
    }

    responsable = {
        "nombre": datos.get("generado_por_nombre") or datos.get("responsable_nombre") or "Equipo VINOVA",
        "rol": datos.get("generado_por_rol") or datos.get("responsable_rol") or "Personal VINOVA",
    }

    empresa = {
        "direccion": "Av. De los Granados E11-67 y De las Hiedras, Quito, Pichincha - Ecuador",
        "correo": "info@vinova.ec",
        "telefono": "+593 2 395 8721",
        "web": "www.vinova.com.ec",
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
            css_src=Path(css_path).as_uri(),
        )

        HTML(string=html_factura, base_url=BASE_DIR).write_pdf(ruta_pdf)
        return ruta_relativa_privada

    except Exception as error:
        print("Advertencia: no se pudo generar PDF profesional con WeasyPrint/plantilla:", error)
        print("Se generará PDF básico de respaldo para no perder la factura.")

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
    content.append("1 1 1 rg")
    content.append(_pdf_text(44, 792, "VINOVA", 28, True))
    content.append(_pdf_text(44, 768, "Factura digital", 12, False))
    content.append(_pdf_text(390, 792, numero_factura, 12, True))
    content.append(_pdf_text(390, 774, f"{factura['fecha_factura']}  {factura['hora_factura']}", 10, False))

    content.append("0.965 0.975 0.995 rg 44 602 516 105 re f")
    content.append("0.750 0.820 0.940 RG 1 w 44 602 516 105 re S")
    content.append("0.020 0.045 0.090 rg")
    content.append(_pdf_text(60, 680, "Cliente", 13, True))
    content.append(_pdf_text(60, 662, f"Nombre: {cliente_nombre}", 10, False))
    content.append(_pdf_text(60, 644, f"Correo: {cliente_correo}", 10, False))
    content.append(_pdf_text(60, 626, f"Local: {factura['establecimiento']}", 10, False))
    content.append(_pdf_text(330, 680, "Vehiculo", 13, True))
    content.append(_pdf_text(330, 662, vehiculo_texto, 10, False))
    content.append(_pdf_text(330, 644, f"Codigo: {vehiculo['codigo_catalogo']}", 10, False))
    content.append(_pdf_text(330, 626, f"Kilometraje: {vehiculo['kilometraje']}", 10, False))

    content.append("0.965 0.975 0.995 rg 44 455 516 120 re f")
    content.append("0.750 0.820 0.940 RG 1 w 44 455 516 120 re S")
    content.append("0.020 0.045 0.090 rg")
    content.append(_pdf_text(60, 548, "Detalle", 13, True))

    y = 524
    for item in items[:5]:
        item_desc = item.get("descripcion", "Servicio VINOVA")
        item_cant = normalizar_precio(item.get("cantidad")) or 1
        item_total = normalizar_precio(item.get("total")) or 0
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

    return ruta_relativa_privada


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
    observaciones="",
):
    """Inserta una factura VINOVA, genera su PDF privado y la deja visible en el perfil."""

    from vinova.core import (
        fecha_actual,
        generar_numero_factura,
        normalizar_fecha,
        normalizar_precio,
        obtener_establecimiento_usuario,
    )

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


def enviar_factura_pdf_segura(factura):
    """Sirve una factura únicamente desde una ruta autorizada por Flask."""

    from vinova.core import app

    if factura["enlace"]:
        return redirect(factura["enlace"])

    ruta_guardada = factura["archivo_pdf"] or factura["archivo"]

    ruta_privada = normalizar_ruta_factura_privada(ruta_guardada)
    if ruta_privada and factura_privada_existe(ruta_privada):
        absoluta = ruta_absoluta_factura_privada(ruta_privada)
        return send_file(
            absoluta,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=os.path.basename(absoluta),
            max_age=0,
        )

    ruta_legacy = normalizar_ruta_factura_static_legacy(ruta_guardada)
    if ruta_legacy:
        ruta_absoluta_legacy = os.path.abspath(os.path.join(app.static_folder, ruta_legacy))
        static_root = os.path.abspath(app.static_folder)
        if ruta_absoluta_legacy.startswith(static_root + os.sep) and os.path.isfile(ruta_absoluta_legacy):
            return send_from_directory(app.static_folder, ruta_legacy, as_attachment=False, max_age=0)

    flash("La factura no tiene archivo disponible.", "warning")
    return redirect(url_for("perfil") + "#seccion-facturas")
