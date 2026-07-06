from vinova.core import *

@app.route("/trabajador")
def trabajador_panel():

    conexion = conectar_db()
    cursor = conexion.cursor()

    editar_id = request.args.get("editar", type=int)
    vehiculo_editar = None
    vehiculo_editar_codigo_existente = False
    manuales_modelo_editar = []

    if editar_id:
        cursor.execute("""
            SELECT *
            FROM vehiculos
            WHERE id = ?
              AND COALESCE(archivado, 0) = 0
        """, (editar_id,))
        vehiculo_editar = cursor.fetchone()

        if not vehiculo_editar:
            conexion.close()
            flash("El vehículo no existe o fue archivado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        cursor.execute("""
            SELECT COUNT(*)
            FROM codigos_vehiculo
            WHERE vehiculo_id = ?
        """, (editar_id,))
        vehiculo_editar_codigo_existente = cursor.fetchone()[0] > 0

        modelo_base_id_editar = vehiculo_editar["modelo_base_id"] if "modelo_base_id" in vehiculo_editar.keys() else None
        if modelo_base_id_editar:
            cursor.execute("""
                SELECT *
                FROM manuales_modelo
                WHERE modelo_id = ?
                ORDER BY id DESC
            """, (modelo_base_id_editar,))
            manuales_modelo_editar = cursor.fetchall()

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

    cursor.execute("""
        SELECT
            manuales_modelo.*,
            vehiculo_modelos.marca,
            vehiculo_modelos.modelo,
            vehiculo_modelos.anio
        FROM manuales_modelo
        INNER JOIN vehiculo_modelos
            ON vehiculo_modelos.id = manuales_modelo.modelo_id
        ORDER BY manuales_modelo.id DESC
    """)
    manuales_admin = cursor.fetchall()

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
        manuales_admin=manuales_admin,
        vehiculo_editar=vehiculo_editar,
        vehiculo_editar_codigo_existente=vehiculo_editar_codigo_existente,
        manuales_modelo_editar=manuales_modelo_editar,
        manual_editar=manuales_modelo_editar[0] if manuales_modelo_editar else None,
        trabajador_establecimiento=trabajador_establecimiento,
        trabajador_generar_codigo_url="/trabajador/vehiculos/__ID__/codigo/generar",
        trabajador_archivar_vehiculo_url="/trabajador/vehiculos/__ID__/archivar",
        trabajador_desarchivar_vehiculo_url="/trabajador/vehiculos/__ID__/desarchivar",
        trabajador_cambiar_estado_vehiculo_url="/trabajador/vehiculos/__ID__/estado",
        trabajador_reactivar_codigo_url="/trabajador/codigos/__ID__/reactivar"
    )


@app.route("/trabajador/vehiculos/<int:vehiculo_id>/estado", methods=["POST"])
def trabajador_cambiar_estado_vehiculo(vehiculo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT activo, estado, COALESCE(archivado, 0) AS archivado
            FROM vehiculos
            WHERE id = ?
        """, (vehiculo_id,))
        vehiculo = cursor.fetchone()

        if not vehiculo:
            flash("Vehículo no encontrado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        if vehiculo["archivado"] == 1:
            flash("No puedes cambiar la visibilidad de un vehículo archivado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        if vehiculo["estado"] == "Vendido":
            if tiene_canje_real(cursor, vehiculo_id):
                flash("Este vehículo fue vendido por canje. Para corregirlo debe reversarse el canje desde administración.", "warning")
                return redirect(url_for("trabajador_panel") + "#trabajador-canjes")

            cursor.execute("""
                UPDATE vehiculos
                SET activo = 1, estado = 'Disponible', actualizado_en = ?
                WHERE id = ?
            """, (fecha_actual(), vehiculo_id))
            nuevo_estado = 1
        else:
            nuevo_estado = 0 if vehiculo["activo"] == 1 else 1
            cursor.execute("""
                UPDATE vehiculos
                SET activo = ?, actualizado_en = ?
                WHERE id = ?
            """, (nuevo_estado, fecha_actual(), vehiculo_id))

        registrar_auditoria(
            conexion,
            "Visibilidad de vehículo actualizada",
            "vehiculo",
            vehiculo_id,
            {"activo": nuevo_estado, "origen": "trabajador"}
        )
        conexion.commit()
        flash("Vehículo activado en el catálogo." if nuevo_estado == 1 else "Vehículo ocultado del catálogo.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar visibilidad desde panel trabajador:", error)
        flash("No se pudo actualizar la visibilidad del vehículo.", "error")

    finally:
        conexion.close()

    return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")


@app.route("/trabajador/vehiculos/<int:vehiculo_id>/desarchivar", methods=["POST"])
def trabajador_desarchivar_vehiculo(vehiculo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()
    ahora = fecha_actual()

    try:
        cursor.execute("""
            SELECT *, COALESCE(archivado, 0) AS archivado_normalizado
            FROM vehiculos
            WHERE id = ?
        """, (vehiculo_id,))
        vehiculo = cursor.fetchone()

        if not vehiculo:
            flash("Vehículo no encontrado.", "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-ocultos")

        if vehiculo["archivado_normalizado"] == 0:
            flash("Este vehículo no está archivado.", "info")
            return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")

        cursor.execute("""
            UPDATE vehiculos
            SET archivado = 0,
                archivado_en = NULL,
                archivado_por = NULL,
                motivo_archivado = NULL,
                activo = 0,
                actualizado_en = ?
            WHERE id = ?
        """, (ahora, vehiculo_id))

        registrar_auditoria(
            conexion,
            "Vehículo desarchivado",
            "vehiculo",
            vehiculo_id,
            {"codigo_catalogo": vehiculo["codigo_catalogo"], "origen": "trabajador", "activo": 0}
        )
        conexion.commit()
        flash("Vehículo desarchivado correctamente. Volvió al listado principal como oculto.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al desarchivar vehículo desde panel trabajador:", error)
        flash("No se pudo desarchivar el vehículo.", "error")

    finally:
        conexion.close()

    return redirect(url_for("trabajador_panel") + "#trabajador-vehiculos")


@app.route("/trabajador/vehiculos/<int:vehiculo_id>/codigo/generar", methods=["POST"])
def trabajador_generar_codigo_vehiculo(vehiculo_id):

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

                registrar_auditoria(
                    conexion,
                    "Código de canje generado",
                    "vehiculo",
                    vehiculo_id,
                    {"codigo": codigo_generado, "origen": "trabajador"}
                )
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
def trabajador_archivar_vehiculo(vehiculo_id):

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

        registrar_auditoria(
            conexion,
            "Vehículo archivado",
            "vehiculo",
            vehiculo_id,
            {"motivo": motivo or "Archivado desde panel trabajador", "origen": "trabajador"}
        )
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
def trabajador_reactivar_codigo_vehiculo(codigo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        codigo, error = reactivar_codigo_vehiculo_seguro(cursor, codigo_id)

        if error:
            conexion.rollback()
            flash(error, "warning")
            return redirect(url_for("trabajador_panel") + "#trabajador-codigos")

        registrar_auditoria(
            conexion,
            "Código de canje reactivado",
            "codigo_vehiculo",
            codigo_id,
            {"codigo": codigo["codigo"], "origen": "trabajador"}
        )
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
def trabajador_crear_usuario():

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
        nuevo_usuario_id = cursor.lastrowid

        registrar_auditoria(
            conexion,
            "Cliente creado",
            "usuario",
            nuevo_usuario_id,
            {"nombre": nombre, "correo": correo, "origen": "trabajador"}
        )
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
def trabajador_actualizar_cedula_usuario(usuario_id):
    """Permite al personal agregar o actualizar la cédula/RUC de un cliente existente."""

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

        registrar_auditoria(
            conexion,
            "Cédula de cliente actualizada",
            "usuario",
            usuario_id,
            {"cliente": usuario["nombre"], "origen": "trabajador"}
        )
        conexion.commit()
        flash(f"Cédula/RUC actualizada para {usuario['nombre']}.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar cédula/RUC desde panel trabajador:", error)
        flash("No se pudo actualizar la cédula/RUC del cliente.", "error")

    finally:
        conexion.close()

    return redirect(destino)
