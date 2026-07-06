from vinova.core import *
from vinova.services.facturas import enviar_factura_pdf_segura, registrar_factura_generada
from vinova.services.inventario import obtener_concesionario_facturacion, recalcular_stock_articulo_concesionarias



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
    subtotal_form = normalizar_precio(request.form.get("monto")) or normalizar_precio(request.form.get("subtotal")) or 0
    impuesto = normalizar_precio(request.form.get("impuesto")) or 0
    cliente_cedula_form = solo_digitos(request.form.get("cliente_cedula", ""))

    articulo_ids = request.form.getlist("articulo_id[]")
    articulo_cantidades = request.form.getlist("articulo_cantidad[]")
    articulos_solicitados = []

    for index, articulo_id_raw in enumerate(articulo_ids):
        try:
            articulo_id = int(articulo_id_raw)
        except (TypeError, ValueError):
            continue

        cantidad_raw = articulo_cantidades[index] if index < len(articulo_cantidades) else "1"
        cantidad = normalizar_precio(cantidad_raw) or 1
        cantidad = max(1, float(cantidad))
        articulos_solicitados.append({"id": articulo_id, "cantidad": cantidad})

    if not usuario_vehiculo_id:
        flash("Selecciona el cliente y vehículo al que pertenece la factura.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        # Si la factura incluye artículos de inventario, bloqueamos escritura para
        # evitar que dos ventas descuenten el mismo stock simultáneamente.
        if articulos_solicitados:
            conexion.execute("BEGIN IMMEDIATE")

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
                vehiculos.anio,
                vehiculos.placa
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

        establecimiento_operativo = obtener_concesionario_facturacion(cursor, session.get("usuario_id"), request.form.get("establecimiento_id", type=int), request.form.get("establecimiento", "").strip() or request.args.get("establecimiento", "").strip())
        establecimiento_id = establecimiento_operativo.get("id") if establecimiento_operativo else None
        establecimiento_nombre = establecimiento_operativo.get("nombre") if establecimiento_operativo else "VINOVA"

        cedula_actual = solo_digitos(registro["usuario_cedula"])
        cedula_factura = cliente_cedula_form or cedula_actual

        if cedula_factura and not validar_identificacion_ec(cedula_factura):
            flash("La cédula o RUC del cliente no es válida.", "warning")
            return redirect(destino)

        if cedula_factura and cedula_factura != cedula_actual:
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
        registro_factura["usuario_cedula"] = cedula_factura or "N/D"
        registro_factura["cedula"] = cedula_factura or "N/D"
        registro_factura["establecimiento"] = establecimiento_nombre
        registro_factura["establecimiento_id"] = establecimiento_id

        items_pdf = []
        articulos_factura = []

        if articulos_solicitados:
            for item in articulos_solicitados:
                if establecimiento_id:
                    cursor.execute("""
                        SELECT articulos.id, articulos.codigo_articulo, articulos.nombre, articulos.categoria,
                               articulos.precio, articulos.unidad, COALESCE(ase.stock, 0) AS stock,
                               COALESCE(articulos.activo, 1) AS activo,
                               COALESCE(articulos.archivado, 0) AS archivado
                        FROM articulos
                        INNER JOIN articulo_stock_establecimiento AS ase
                            ON ase.articulo_id = articulos.id
                           AND ase.establecimiento_id = ?
                        WHERE articulos.id = ?
                        LIMIT 1
                    """, (establecimiento_id, item["id"]))
                else:
                    cursor.execute("""
                        SELECT id, codigo_articulo, nombre, categoria, precio, stock, unidad,
                               COALESCE(activo, 1) AS activo,
                               COALESCE(archivado, 0) AS archivado
                        FROM articulos
                        WHERE id = ?
                        LIMIT 1
                    """, (item["id"],))
                articulo = cursor.fetchone()

                if not articulo or articulo["archivado"] == 1 or articulo["activo"] != 1:
                    raise ValueError("Uno de los artículos seleccionados ya no está disponible.")

                stock_actual = normalizar_precio(articulo["stock"]) or 0
                cantidad = item["cantidad"]

                if cantidad > stock_actual:
                    sede_stock = f" en {establecimiento_nombre}" if establecimiento_nombre else ""
                    raise ValueError(f"Stock insuficiente para {articulo['nombre']}{sede_stock}. Disponible: {stock_actual:g} {articulo['unidad'] or 'Unidad'}.")

                precio_unitario = normalizar_precio(articulo["precio"]) or 0
                total_item = cantidad * precio_unitario

                articulos_factura.append({
                    "id": articulo["id"],
                    "codigo_articulo": articulo["codigo_articulo"],
                    "nombre": articulo["nombre"],
                    "categoria": articulo["categoria"],
                    "cantidad": cantidad,
                    "unidad": articulo["unidad"] or "Unidad",
                    "precio_unitario": precio_unitario,
                    "total": total_item,
                    "stock_anterior": stock_actual,
                    "stock_nuevo": stock_actual - cantidad,
                    "establecimiento_id": establecimiento_id,
                    "establecimiento": establecimiento_nombre,
                })

                items_pdf.append({
                    "descripcion": f"{articulo['nombre']} ({articulo['codigo_articulo']})",
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "total": total_item,
                })

            subtotal = sum(item["total"] for item in articulos_factura)
            concepto = concepto if concepto != "Factura manual VINOVA" else "Venta de artículos VINOVA"
            descripcion = descripcion if descripcion != concepto else "; ".join(f"{item['nombre']} x {item['cantidad']:g}" for item in articulos_factura)
        else:
            subtotal = subtotal_form

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
            items=items_pdf,
            observaciones=observaciones
        )

        if articulos_factura:
            ahora = fecha_actual()

            for item in articulos_factura:
                cursor.execute("""
                    INSERT INTO factura_articulos (
                        factura_id, articulo_id, codigo_articulo, nombre_articulo, categoria,
                        cantidad, unidad, precio_unitario, total, creado_en
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    factura_id,
                    item["id"],
                    item["codigo_articulo"],
                    item["nombre"],
                    item["categoria"],
                    item["cantidad"],
                    item["unidad"],
                    item["precio_unitario"],
                    item["total"],
                    ahora,
                ))

                if item.get("establecimiento_id"):
                    cursor.execute("""
                        UPDATE articulo_stock_establecimiento
                        SET stock = ?,
                            unidades_vendidas = COALESCE(unidades_vendidas, 0) + ?,
                            actualizado_en = ?
                        WHERE articulo_id = ? AND establecimiento_id = ?
                    """, (
                        item["stock_nuevo"],
                        item["cantidad"],
                        ahora,
                        item["id"],
                        item["establecimiento_id"],
                    ))
                    recalcular_stock_articulo_concesionarias(cursor, item["id"], session.get("usuario_id"))
                else:
                    cursor.execute("""
                        UPDATE articulos
                        SET stock = ?,
                            unidades_vendidas = COALESCE(unidades_vendidas, 0) + ?,
                            estado = CASE WHEN ? <= 0 THEN 'Agotado' ELSE estado END,
                            actualizado_por = ?,
                            actualizado_en = ?
                        WHERE id = ?
                    """, (
                        item["stock_nuevo"],
                        item["cantidad"],
                        item["stock_nuevo"],
                        session.get("usuario_id"),
                        ahora,
                        item["id"],
                    ))

                try:
                    cursor.execute("""
                        INSERT INTO articulo_movimientos (
                            articulo_id, establecimiento_id, tipo_movimiento, cantidad,
                            stock_anterior, stock_nuevo, referencia_tipo, referencia_id,
                            descripcion, creado_por, creado_en
                        )
                        VALUES (?, ?, 'venta', ?, ?, ?, 'factura', ?, ?, ?, ?)
                    """, (
                        item["id"],
                        item.get("establecimiento_id"),
                        -item["cantidad"],
                        item["stock_anterior"],
                        item["stock_nuevo"],
                        factura_id,
                        f"Venta en factura {factura_id} - {establecimiento_nombre}",
                        session.get("usuario_id"),
                        ahora,
                    ))
                except sqlite3.OperationalError:
                    cursor.execute("""
                        INSERT INTO articulo_movimientos (
                            articulo_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo,
                            referencia_tipo, referencia_id, descripcion, creado_por, creado_en
                        )
                        VALUES (?, 'venta', ?, ?, ?, 'factura', ?, ?, ?, ?)
                    """, (
                        item["id"],
                        -item["cantidad"],
                        item["stock_anterior"],
                        item["stock_nuevo"],
                        factura_id,
                        f"Venta en factura {factura_id} - {establecimiento_nombre}",
                        session.get("usuario_id"),
                        ahora,
                    ))

        registrar_auditoria(
            conexion,
            "Factura generada",
            "factura",
            factura_id,
            {
                "usuario_vehiculo_id": usuario_vehiculo_id,
                "tipo_factura": tipo_factura,
                "origen": origen,
                "articulos": len(articulos_factura),
            }
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

    except ValueError as error:
        conexion.rollback()
        flash(str(error), "warning")

    except sqlite3.OperationalError as error:
        conexion.rollback()
        print("Error SQL al generar factura:", error)
        flash("No se pudo generar la factura. Verifica que ejecutaste la migración de artículos si estás vendiendo inventario.", "error")

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

    if not session.get("usuario_id"):
        flash("Inicia sesión para ver esta factura.", "warning")
        return redirect(url_for("login"))

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

    return enviar_factura_pdf_segura(factura)
