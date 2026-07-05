from vinova.core import *

@app.route("/facturas/guardar", methods=["POST"])
def guardar_factura_vehiculo():

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

        factura_id = registrar_factura_generada(
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

        registrar_auditoria(
            conexion,
            "Factura generada",
            "factura",
            factura_id,
            {"usuario_vehiculo_id": usuario_vehiculo_id, "tipo_factura": tipo_factura, "origen": origen}
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
def admin_cambiar_estado_factura(factura_id):

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

        registrar_auditoria(
            conexion,
            "Estado de factura actualizado",
            "factura",
            factura_id,
            {"activo": nuevo_estado, "motivo": motivo or ""}
        )
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
def ver_factura_vehiculo(factura_id):

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
