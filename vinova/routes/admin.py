from vinova.core import *

@app.route("/admin")
def admin_inicio():
    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos")
def admin_vehiculos():

    editar_id = request.args.get("editar", type=int)
    editar_establecimiento_id = request.args.get("editar_establecimiento", type=int)

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
    manuales_modelo_editar = []

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

    recursos_static_admin = listar_recursos_static_bd(cursor)

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

    usuarios_notificacion_admin = [
        dict(usuario)
        for usuario in usuarios_admin
        if int(usuario["activo"] or 0) == 1
    ]

    notificaciones_enviadas_admin = listar_notificaciones_enviadas(
        cursor,
        remitente_id=None,
        solo_clientes=False,
        limite=60
    )

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

    establecimientos_admin = listar_establecimientos(cursor, incluir_inactivos=True)
    establecimientos_activos = listar_establecimientos(cursor, incluir_inactivos=False)
    establecimiento_editar = None

    if editar_establecimiento_id:
        establecimiento_editar = obtener_establecimiento_por_id(cursor, editar_establecimiento_id, incluir_inactivos=True)
        if not establecimiento_editar:
            flash("El establecimiento no existe o no está disponible.", "warning")

    cursor.execute("""
        SELECT
            auditoria_acciones.*
        FROM auditoria_acciones
        WHERE UPPER(COALESCE(usuario_rol, '')) IN ('ADMIN', 'TRABAJADOR')
          AND LOWER(COALESCE(accion, '')) NOT LIKE '%inicio de sesi%n%'
          AND LOWER(COALESCE(accion, '')) NOT LIKE '%login%'
        ORDER BY datetime(creado_en) DESC, id DESC
        LIMIT 180
    """)
    auditoria_admin = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*)
        FROM auditoria_acciones
        WHERE UPPER(COALESCE(usuario_rol, '')) IN ('ADMIN', 'TRABAJADOR')
          AND LOWER(COALESCE(accion, '')) NOT LIKE '%inicio de sesi%n%'
          AND LOWER(COALESCE(accion, '')) NOT LIKE '%login%'
    """)
    total_auditoria = cursor.fetchone()[0]

    total_usuarios = len(usuarios_admin)
    total_trabajadores = len(trabajadores_admin)

    conexion.close()

    return render_template(
        "admin.html",
        vehiculos=vehiculos,
        vehiculo_editar=vehiculo_editar,
        manuales_modelo_editar=manuales_modelo_editar,
        manual_editar=manuales_modelo_editar[0] if manuales_modelo_editar else None,
        total_vehiculos=total_vehiculos,
        vehiculos_activos=vehiculos_activos,
        vehiculos_inactivos=vehiculos_inactivos,
        vehiculos_archivados_total=vehiculos_archivados_total,
        vehiculos_archivados=vehiculos_archivados,
        ventas_canje=ventas_canje,
        usuarios_admin=usuarios_admin,
        usuarios_notificacion_admin=usuarios_notificacion_admin,
        notificaciones_enviadas_admin=notificaciones_enviadas_admin,
        trabajadores_admin=trabajadores_admin,
        canjes_reversados=canjes_reversados,
        total_usuarios=total_usuarios,
        total_trabajadores=total_trabajadores,
        codigos_por_vehiculo=codigos_por_vehiculo,
        vehiculos_clientes=vehiculos_clientes,
        mantenimientos=mantenimientos,
        total_mantenimientos=total_mantenimientos,
        manuales_admin=manuales_admin,
        recursos_static_admin=recursos_static_admin,
        facturas_admin=facturas_admin,
        total_facturas=total_facturas,
        establecimientos_admin=establecimientos_admin,
        establecimientos_activos=establecimientos_activos,
        establecimiento_editar=establecimiento_editar,
        tipos_establecimiento=TIPOS_ESTABLECIMIENTO,
        auditoria_admin=auditoria_admin,
        total_auditoria=total_auditoria,
        maptiler_key=os.getenv("MAPTILER_KEY", "")
    )


@app.route("/admin/vehiculos/guardar", methods=["POST"])
@app.route("/vehiculos/guardar", methods=["POST"])
def admin_guardar_vehiculo():

    origen = request.form.get("origen", "admin").strip().lower()
    vehiculo_id = request.form.get("vehiculo_id", "").strip()

    codigo_catalogo = request.form.get("codigo_catalogo", "").strip().upper()
    placa = normalizar_placa_vehiculo(request.form.get("placa", ""))
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
    modelo_3d = normalizar_ruta_static_documento(request.form.get("modelo_3d", "")) or request.form.get("modelo_3d", "").strip()
    modelo_3d_tipo = request.form.get("modelo_3d_tipo", "glb").strip()
    imagen_existente = normalizar_ruta_static_documento(request.form.get("imagen_existente", ""))
    modelo_3d_existente = normalizar_ruta_static_documento(request.form.get("modelo_3d_existente", ""))
    if modelo_3d_existente:
        modelo_3d = modelo_3d_existente
        modelo_3d_tipo = modelo_3d_existente.rsplit(".", 1)[1].lower() if "." in modelo_3d_existente else "glb"
    preview_sistemas_json_raw = request.form.get("preview_sistemas_json", "").strip()

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

    if not marca or not modelo or not anio:
        flash("Marca, modelo y año son obligatorios. El código de catálogo puede generarse automáticamente.", "warning")
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
    archivo_modelo_3d = request.files.get("modelo_3d_file")

    try:
        preview_sistemas_json = normalizar_preview_sistemas_json(preview_sistemas_json_raw)
    except ValueError as error:
        flash(str(error), "warning")
        return redirigir_operativo("vehiculos", origen)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()

        if not codigo_catalogo:
            codigo_catalogo = generar_codigo_catalogo(cursor, marca, modelo, anio, vehiculo_id or None)

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

        try:
            modelo_3d_guardado = guardar_modelo_3d_local(archivo_modelo_3d, marca, modelo, anio)
        except ValueError as error:
            flash(str(error), "warning")
            return redirigir_operativo("vehiculos", origen)

        if modelo_3d_guardado:
            modelo_3d = modelo_3d_guardado
            modelo_3d_tipo = modelo_3d_guardado.rsplit(".", 1)[1].lower()

        if modelo_3d and not modelo_3d_id:
            modelo_3d_id = crear_slug(f"{marca}-{modelo}-{anio}")

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
            preview_sistemas_json,
            session.get("usuario_id")
        )
        modelo_base_id = modelo_base["id"]
        modelo_3d = modelo_base.get("modelo_3d", "")
        modelo_3d_id = modelo_base.get("modelo_3d_id", "")
        modelo_3d_tipo = modelo_base.get("modelo_3d_tipo", modelo_3d_tipo)
        preview_sistemas_json = modelo_base.get("preview_sistemas_json", preview_sistemas_json)

        try:
            imagen_guardada = guardar_imagen_vehiculo(archivo_imagen, codigo_catalogo)
        except ValueError as error:
            flash(str(error), "warning")
            return redirigir_operativo("vehiculos", origen)

        if vehiculo_id:

            imagen_final = imagen_guardada or imagen_existente or vehiculo_actual["imagen"] or ""

            if imagen_final != (vehiculo_actual["imagen"] or ""):
                cursor.execute("""
                    UPDATE vehiculos
                    SET
                        codigo_catalogo = ?,
                        placa = ?,
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
                        preview_sistemas_json = ?,
                        descripcion = ?,
                        estado = ?,
                        activo = ?,
                        actualizado_en = ?
                    WHERE id = ?
                """, (
                    codigo_catalogo,
                    placa,
                    marca,
                    modelo,
                    anio,
                    tipo_vehiculo,
                    combustible,
                    transmision,
                    kilometraje,
                    precio,
                    imagen_final,
                    modelo_base_id,
                    modelo_3d,
                    modelo_3d_id,
                    modelo_3d_tipo,
                    preview_sistemas_json,
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
                        placa = ?,
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
                        preview_sistemas_json = ?,
                        descripcion = ?,
                        estado = ?,
                        activo = ?,
                        actualizado_en = ?
                    WHERE id = ?
                """, (
                    codigo_catalogo,
                    placa,
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
                    preview_sistemas_json,
                    descripcion,
                    estado,
                    activo,
                    ahora,
                    vehiculo_id
                ))

            if imagen_final != (vehiculo_actual["imagen"] or ""):
                eliminar_archivo_static_si_no_referenciado(cursor, vehiculo_actual["imagen"])

            if modelo_3d != (vehiculo_actual["modelo_3d"] or ""):
                eliminar_archivo_static_si_no_referenciado(cursor, vehiculo_actual["modelo_3d"])

            flash("Vehículo actualizado correctamente.", "success")

        else:
            cursor.execute("""
                INSERT INTO vehiculos (
                    codigo_catalogo,
                    placa,
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
                    preview_sistemas_json,
                    descripcion,
                    estado,
                    activo,
                    creado_por,
                    creado_en,
                    archivado
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo_catalogo,
                placa,
                marca,
                modelo,
                anio,
                tipo_vehiculo,
                combustible,
                transmision,
                kilometraje,
                precio,
                imagen_guardada or imagen_existente or "",
                modelo_base_id,
                modelo_3d,
                modelo_3d_id,
                modelo_3d_tipo,
                preview_sistemas_json,
                descripcion,
                estado,
                activo,
                session["usuario_id"],
                ahora,
                0
            ))

            vehiculo_id = cursor.lastrowid
            flash("Vehículo creado correctamente.", "success")

        guardar_manual_modelo_desde_form(cursor, modelo_base_id, session.get("usuario_id"))

        registrar_auditoria(
            conexion,
            "Vehículo actualizado" if request.form.get("vehiculo_id", type=int) else "Vehículo creado",
            "vehiculo",
            vehiculo_id,
            {"codigo_catalogo": codigo_catalogo, "placa": placa or "N/D", "marca": marca, "modelo": modelo, "anio": anio, "origen": origen}
        )
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
def admin_cambiar_estado_vehiculo(vehiculo_id):

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

        registrar_auditoria(
            conexion,
            "Venta manual corregida",
            "vehiculo",
            vehiculo_id,
            {"nuevo_estado": "Disponible", "activo": 1}
        )
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

    registrar_auditoria(
        conexion,
        "Visibilidad de vehículo actualizada",
        "vehiculo",
        vehiculo_id,
        {"activo": nuevo_estado}
    )
    conexion.commit()
    conexion.close()

    if nuevo_estado == 1:
        flash("Vehículo activado en el catálogo.", "success")
    else:
        flash("Vehículo ocultado del catálogo.", "success")

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/codigo/generar", methods=["POST"])
def admin_generar_codigo_vehiculo(vehiculo_id):

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

                registrar_auditoria(
                    conexion,
                    "Código de canje generado",
                    "vehiculo",
                    vehiculo_id,
                    {"codigo": codigo_generado, "origen": "admin"}
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
        print("Error al generar código de canje:", error)
        flash("No se pudo generar el código de canje.", "error")

    finally:
        conexion.close()

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/archivar", methods=["POST"])
def admin_archivar_vehiculo(vehiculo_id):

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

        registrar_auditoria(
            conexion,
            "Vehículo archivado",
            "vehiculo",
            vehiculo_id,
            {"motivo": motivo or "Archivado manualmente desde administración", "origen": "admin"}
        )
        conexion.commit()
        flash("Vehículo archivado correctamente. Se conservará en el historial interno y sus códigos pendientes quedaron desactivados.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al archivar vehículo:", error)
        flash("No se pudo archivar el vehículo.", "error")

    finally:
        conexion.close()

    return redirigir_admin("archivados")


@app.route("/admin/vehiculos/<int:vehiculo_id>/desarchivar", methods=["POST"])
def admin_desarchivar_vehiculo(vehiculo_id):

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
            return redirigir_admin("archivados")

        if vehiculo["archivado_normalizado"] == 0:
            flash("Este vehículo no está archivado.", "info")
            return redirigir_admin("vehiculos")

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
            {"codigo_catalogo": vehiculo["codigo_catalogo"], "origen": "admin", "activo": 0}
        )
        conexion.commit()
        flash("Vehículo desarchivado correctamente. Volvió al listado principal como oculto.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al desarchivar vehículo desde admin:", error)
        flash("No se pudo desarchivar el vehículo.", "error")

    finally:
        conexion.close()

    return redirigir_admin("vehiculos")


@app.route("/admin/vehiculos/<int:vehiculo_id>/eliminar-permanente", methods=["POST"])
def admin_eliminar_vehiculo_permanente(vehiculo_id):
    """Elimina definitivamente un vehículo archivado y limpia archivos no compartidos."""

    conexion = conectar_db()
    cursor = conexion.cursor()
    recursos_a_revisar = set()

    def tabla_columna(tabla, columna):
        return tabla_existe_db(cursor, tabla) and columna_existe_db(cursor, tabla, columna)

    def borrar_where(tabla, where, params=()):
        if tabla_existe_db(cursor, tabla):
            cursor.execute(f"DELETE FROM {tabla} WHERE {where}", params)

    def recolectar_columna(tabla, columna, where, params=()):
        if tabla_columna(tabla, columna):
            cursor.execute(f"SELECT {columna} FROM {tabla} WHERE {where}", params)
            for fila in cursor.fetchall():
                ruta = normalizar_ruta_static_documento(fila[columna])
                if ruta:
                    recursos_a_revisar.add(ruta)

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            SELECT *, COALESCE(archivado, 0) AS archivado_normalizado
            FROM vehiculos
            WHERE id = ?
        """, (vehiculo_id,))
        vehiculo = cursor.fetchone()

        if not vehiculo:
            conexion.rollback()
            flash("Vehículo no encontrado.", "warning")
            return redirigir_admin("archivados")

        if vehiculo["archivado_normalizado"] != 1:
            conexion.rollback()
            flash("Solo puedes eliminar permanentemente vehículos que ya estén archivados.", "warning")
            return redirigir_admin("vehiculos")

        for campo in ("imagen", "modelo_3d"):
            ruta = normalizar_ruta_static_documento(vehiculo[campo] if campo in vehiculo.keys() else "")
            if ruta:
                recursos_a_revisar.add(ruta)

        recolectar_columna("manuales_vehiculo", "archivo", "vehiculo_id = ?", (vehiculo_id,))
        recolectar_columna("facturas_vehiculo", "archivo", "vehiculo_id = ?", (vehiculo_id,))

        usuario_vehiculo_ids = []
        if tabla_columna("usuarios_vehiculos", "id") and columna_existe_db(cursor, "usuarios_vehiculos", "vehiculo_id"):
            cursor.execute("SELECT id FROM usuarios_vehiculos WHERE vehiculo_id = ?", (vehiculo_id,))
            usuario_vehiculo_ids = [fila["id"] for fila in cursor.fetchall()]

        factura_ids = []
        if tabla_columna("facturas_vehiculo", "id") and columna_existe_db(cursor, "facturas_vehiculo", "vehiculo_id"):
            cursor.execute("SELECT id FROM facturas_vehiculo WHERE vehiculo_id = ?", (vehiculo_id,))
            factura_ids = [fila["id"] for fila in cursor.fetchall()]

        for factura_id in factura_ids:
            borrar_where("factura_articulos", "factura_id = ?", (factura_id,))

        modelo_base_id = vehiculo["modelo_base_id"] if "modelo_base_id" in vehiculo.keys() else None
        eliminar_modelo_base = False
        if modelo_base_id:
            cursor.execute("""
                SELECT COUNT(*)
                FROM vehiculos
                WHERE modelo_base_id = ?
                  AND id != ?
            """, (modelo_base_id, vehiculo_id))
            eliminar_modelo_base = int(cursor.fetchone()[0] or 0) == 0

        if eliminar_modelo_base:
            recolectar_columna("vehiculo_modelos", "modelo_3d", "id = ?", (modelo_base_id,))
            recolectar_columna("manuales_modelo", "archivo", "modelo_id = ?", (modelo_base_id,))
            borrar_where("manuales_modelo", "modelo_id = ?", (modelo_base_id,))
            borrar_where("vehiculo_modelos", "id = ?", (modelo_base_id,))

        borrar_where("manuales_vehiculo", "vehiculo_id = ?", (vehiculo_id,))
        borrar_where("facturas_vehiculo", "vehiculo_id = ?", (vehiculo_id,))
        borrar_where("mantenimientos", "vehiculo_id = ?", (vehiculo_id,))
        borrar_where("canjes_reversados", "vehiculo_id = ?", (vehiculo_id,))
        for usuario_vehiculo_id in usuario_vehiculo_ids:
            borrar_where("canjes_reversados", "usuario_vehiculo_id = ?", (usuario_vehiculo_id,))
        borrar_where("usuarios_vehiculos", "vehiculo_id = ?", (vehiculo_id,))
        borrar_where("codigos_vehiculo", "vehiculo_id = ?", (vehiculo_id,))
        borrar_where("vehiculos", "id = ?", (vehiculo_id,))

        archivos_borrados = []
        for recurso in sorted(recursos_a_revisar):
            if eliminar_archivo_static_si_no_referenciado(cursor, recurso):
                archivos_borrados.append(recurso)

        registrar_auditoria(
            conexion,
            "Vehículo eliminado permanentemente",
            "vehiculo",
            vehiculo_id,
            {
                "codigo_catalogo": vehiculo["codigo_catalogo"],
                "marca": vehiculo["marca"],
                "modelo": vehiculo["modelo"],
                "anio": vehiculo["anio"],
                "archivos_borrados": archivos_borrados,
            },
        )
        conexion.commit()
        flash("Vehículo eliminado permanentemente. Los archivos locales no compartidos también fueron limpiados.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al eliminar vehículo permanentemente:", error)
        flash("No se pudo eliminar permanentemente el vehículo.", "error")

    finally:
        conexion.close()

    return redirigir_admin("archivados")


@app.route("/admin/canjes/<int:usuario_vehiculo_id>/reversar", methods=["POST"])
def admin_reversar_canje(usuario_vehiculo_id):

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

        registrar_auditoria(
            conexion,
            "Canje reversado",
            "usuario_vehiculo",
            usuario_vehiculo_id,
            {"vehiculo_id": canje["vehiculo_id"], "codigo": canje["codigo_canje"], "motivo": motivo or "Reversa administrativa de canje"}
        )
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

    registrar_auditoria(
        conexion,
        "Código de canje desactivado",
        "codigo_vehiculo",
        codigo_id,
        {"codigo": codigo["codigo"]}
    )
    conexion.commit()
    conexion.close()

    flash("Código de canje desactivado correctamente.", "success")
    return redirigir_admin("vehiculos")


@app.route("/admin/codigos/<int:codigo_id>/reactivar", methods=["POST"])
def admin_reactivar_codigo_vehiculo(codigo_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        codigo, error = reactivar_codigo_vehiculo_seguro(cursor, codigo_id)

        if error:
            conexion.rollback()
            flash(error, "warning")
            return redirigir_admin("codigos")

        registrar_auditoria(
            conexion,
            "Código de canje reactivado",
            "codigo_vehiculo",
            codigo_id,
            {"codigo": codigo["codigo"], "origen": "admin"}
        )
        conexion.commit()
        flash(f"Código de canje reactivado correctamente: {codigo['codigo']}", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al reactivar código de canje:", error)
        flash("No se pudo reactivar el código de canje.", "error")

    finally:
        conexion.close()

    return redirigir_admin("codigos")


@app.route("/admin/usuarios/crear", methods=["POST"])
def admin_crear_usuario():

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

    if rol == "TRABAJADOR":
        establecimiento_registrado = establecimiento_activo_por_nombre(cursor, establecimiento)
        if not establecimiento_registrado:
            conexion.close()
            flash("Selecciona un establecimiento activo para el trabajador.", "warning")
            return redirigir_admin("trabajadores")
        establecimiento = establecimiento_registrado["nombre"]

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
        nuevo_usuario_id = cursor.lastrowid

        registrar_auditoria(
            conexion,
            "Usuario creado por administración",
            "usuario",
            nuevo_usuario_id,
            {"nombre": nombre, "correo": correo, "rol": rol}
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
def admin_actualizar_rol_usuario(usuario_id):

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

        registrar_auditoria(
            conexion,
            "Rol de usuario actualizado",
            "usuario",
            usuario_id,
            {"rol_anterior": usuario["rol"], "rol_nuevo": nuevo_rol}
        )
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
def admin_cambiar_estado_usuario(usuario_id):

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

        registrar_auditoria(
            conexion,
            "Estado de usuario actualizado",
            "usuario",
            usuario_id,
            {"activo": nuevo_estado, "nombre": usuario["nombre"]}
        )
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



@app.route("/admin/notificaciones/buscar-usuarios", endpoint="admin_buscar_usuarios_notificacion")
def admin_buscar_usuarios_notificacion():

    termino = request.args.get("q", "").strip()
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        resultados = buscar_destinatarios_notificacion(
            cursor,
            termino,
            solo_clientes=False,
            limite=12
        )
        return jsonify({"resultados": resultados})

    except Exception as error:
        print("Error al buscar destinatarios desde admin:", error)
        return jsonify({"resultados": [], "error": "No se pudo buscar usuarios."}), 500

    finally:
        conexion.close()


@app.route("/admin/notificaciones/enviar", methods=["POST"])
def admin_enviar_notificacion_usuario():

    usuario_id = request.form.get("usuario_id", type=int)
    tipo = normalizar_tipo_notificacion(request.form.get("tipo"))
    prioridad = normalizar_prioridad_notificacion(request.form.get("prioridad"))
    titulo = request.form.get("titulo", "").strip()
    mensaje = request.form.get("mensaje", "").strip()

    if not usuario_id:
        flash("Selecciona el usuario que recibirá la notificación.", "warning")
        return redirigir_admin("mensajes")

    if not titulo or not mensaje:
        flash("Completa título y mensaje de la notificación.", "warning")
        return redirigir_admin("mensajes")

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, correo, rol, COALESCE(activo, 1) AS activo
            FROM usuarios
            WHERE id = ?
            LIMIT 1
        """, (usuario_id,))
        usuario_destino = cursor.fetchone()

        if not usuario_destino:
            flash("El usuario seleccionado no existe.", "warning")
            return redirigir_admin("mensajes")

        if int(usuario_destino["activo"] or 0) != 1:
            flash("No puedes enviar notificaciones a una cuenta inactiva.", "warning")
            return redirigir_admin("mensajes")

        notificacion_id = crear_notificacion_usuario(
            conexion,
            usuario_id=usuario_destino["id"],
            remitente_id=session.get("usuario_id"),
            tipo=tipo,
            prioridad=prioridad,
            titulo=titulo,
            mensaje=mensaje,
        )

        if not notificacion_id:
            flash("No se pudo crear la notificación. Revisa título y mensaje.", "warning")
            return redirigir_admin("mensajes")

        registrar_auditoria(
            conexion,
            "Notificación enviada a usuario",
            "notificacion_usuario",
            notificacion_id,
            {
                "usuario_id": usuario_destino["id"],
                "usuario_correo": usuario_destino["correo"],
                "tipo": tipo,
                "prioridad": prioridad,
            }
        )
        conexion.commit()
        flash(f"Notificación enviada a {usuario_destino['nombre']}.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al enviar notificación desde admin:", error)
        flash("No se pudo enviar la notificación.", "error")

    finally:
        conexion.close()

    return redirigir_admin("mensajes")


@app.route("/admin/trabajadores/<int:trabajador_id>/establecimiento", methods=["POST"])
def admin_actualizar_establecimiento_trabajador(trabajador_id):

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

        establecimiento_registrado = establecimiento_activo_por_nombre(cursor, establecimiento)
        if not establecimiento_registrado:
            flash("Selecciona un establecimiento activo para el trabajador.", "warning")
            return redirigir_admin("trabajadores")

        establecimiento = establecimiento_registrado["nombre"]

        cursor.execute("""
            UPDATE usuarios
            SET establecimiento = ?, actualizado_en = ?
            WHERE id = ?
        """, (
            establecimiento,
            fecha_actual(),
            trabajador_id
        ))

        registrar_auditoria(
            conexion,
            "Establecimiento de trabajador actualizado",
            "usuario",
            trabajador_id,
            {"establecimiento": establecimiento}
        )
        conexion.commit()
        flash("Establecimiento del trabajador actualizado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar establecimiento:", error)
        flash("No se pudo actualizar el establecimiento.", "error")

    finally:
        conexion.close()

    return redirigir_admin("trabajadores")



@app.route("/admin/establecimientos/guardar", methods=["POST"])
def admin_guardar_establecimiento():

    establecimiento_id = request.form.get("establecimiento_id", type=int)
    nombre = request.form.get("nombre", "").strip()
    tipo = request.form.get("tipo", "concesionario").strip()
    descripcion = request.form.get("descripcion", "").strip()
    direccion = request.form.get("direccion", "").strip()
    ciudad = request.form.get("ciudad", "").strip()
    provincia = request.form.get("provincia", "").strip()
    telefono = request.form.get("telefono", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    horario = request.form.get("horario", "").strip()
    website = request.form.get("website", "").strip()
    imagen_manual = normalizar_ruta_static_documento(request.form.get("imagen", ""))
    archivo_imagen = request.files.get("imagen_file")
    quitar_imagen = request.form.get("quitar_imagen") == "on"
    servicios = request.form.get("servicios", "").strip()
    distancia_km = normalizar_precio(request.form.get("distancia_km"))
    lat = normalizar_coordenada(request.form.get("lat"), -90, 90)
    lng = normalizar_coordenada(request.form.get("lng"), -180, 180)
    pin_x = normalizar_precio(request.form.get("pin_x"))
    pin_y = normalizar_precio(request.form.get("pin_y"))
    activo = 1 if request.form.get("activo") == "on" else 0

    if tipo not in TIPOS_ESTABLECIMIENTO:
        flash("Tipo de establecimiento no permitido.", "warning")
        return redirigir_admin("establecimientos")

    if not nombre or not direccion:
        flash("Nombre y dirección son obligatorios para registrar un establecimiento.", "warning")
        return redirigir_admin("establecimientos")

    if correo and "@" not in correo:
        flash("Ingresa un correo válido para el establecimiento.", "warning")
        return redirigir_admin("establecimientos")

    if distancia_km is None:
        distancia_km = 0
    if pin_x is None:
        pin_x = 50
    if pin_y is None:
        pin_y = 50

    pin_x = max(4, min(96, pin_x))
    pin_y = max(4, min(96, pin_y))
    servicios_json = serializar_servicios_establecimiento(servicios)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()
        establecimiento_actual = None

        if establecimiento_id:
            cursor.execute("SELECT * FROM establecimientos WHERE id = ?", (establecimiento_id,))
            establecimiento_actual = cursor.fetchone()
            if not establecimiento_actual:
                flash("El establecimiento que intentas editar no existe.", "warning")
                return redirigir_admin("establecimientos")

        if establecimiento_actual:
            lat_actual = normalizar_coordenada(establecimiento_actual["lat"], -90, 90) if "lat" in establecimiento_actual.keys() else None
            lng_actual = normalizar_coordenada(establecimiento_actual["lng"], -180, 180) if "lng" in establecimiento_actual.keys() else None

            if lat is None:
                lat = lat_actual
            if lng is None:
                lng = lng_actual

        if lat is None or lng is None or (lat == 0 and lng == 0):
            lat = DEFAULT_ESTABLECIMIENTO_LAT
            lng = DEFAULT_ESTABLECIMIENTO_LNG

        try:
            imagen_guardada = guardar_imagen_establecimiento(archivo_imagen, nombre, tipo)
        except ValueError as error:
            flash(str(error), "warning")
            return redirigir_admin("establecimientos")

        imagen_actual = (
            establecimiento_actual["imagen"]
            if establecimiento_actual and "imagen" in establecimiento_actual.keys()
            else ""
        )
        imagen = "" if quitar_imagen else (imagen_guardada or imagen_manual or imagen_actual)

        if establecimiento_id:
            cursor.execute("""
                UPDATE establecimientos
                SET nombre = ?, tipo = ?, descripcion = ?, direccion = ?, ciudad = ?, provincia = ?,
                    telefono = ?, correo = ?, horario = ?, website = ?, imagen = ?, servicios = ?,
                    distancia_km = ?, lat = ?, lng = ?, pin_x = ?, pin_y = ?, activo = ?,
                    actualizado_por = ?, actualizado_en = ?
                WHERE id = ?
            """, (
                nombre, tipo, descripcion, direccion, ciudad, provincia,
                telefono, correo, horario, website, imagen, servicios_json,
                distancia_km, lat, lng, pin_x, pin_y, activo,
                session.get("usuario_id"), ahora, establecimiento_id
            ))
            accion = "Establecimiento actualizado"
            entidad_id = establecimiento_id
            flash("Establecimiento actualizado correctamente.", "success")
        else:
            cursor.execute("""
                INSERT INTO establecimientos (
                    nombre, tipo, descripcion, direccion, ciudad, provincia,
                    telefono, correo, horario, website, imagen, servicios,
                    distancia_km, lat, lng, pin_x, pin_y, activo,
                    creado_por, actualizado_por, creado_en, actualizado_en
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nombre, tipo, descripcion, direccion, ciudad, provincia,
                telefono, correo, horario, website, imagen, servicios_json,
                distancia_km, lat, lng, pin_x, pin_y, activo,
                session.get("usuario_id"), session.get("usuario_id"), ahora, ahora
            ))
            entidad_id = cursor.lastrowid
            accion = "Establecimiento creado"
            flash("Establecimiento agregado correctamente al mapa.", "success")

        registrar_auditoria(
            conexion,
            accion,
            "establecimiento",
            entidad_id,
            {"nombre": nombre, "tipo": tipo, "activo": activo}
        )
        conexion.commit()

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe un establecimiento con ese nombre.", "warning")
    except sqlite3.OperationalError as error:
        conexion.rollback()
        print("Error al guardar establecimiento:", error)
        flash("No se pudo guardar. Verifica que ejecutaste la migración de establecimientos.", "error")
    except Exception as error:
        conexion.rollback()
        print("Error al guardar establecimiento:", error)
        flash("No se pudo guardar el establecimiento.", "error")
    finally:
        conexion.close()

    return redirigir_admin("establecimientos")


@app.route("/admin/establecimientos/<int:establecimiento_id>/estado", methods=["POST"])
def admin_cambiar_estado_establecimiento(establecimiento_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, COALESCE(activo, 1) AS activo
            FROM establecimientos
            WHERE id = ?
        """, (establecimiento_id,))
        establecimiento = cursor.fetchone()

        if not establecimiento:
            flash("Establecimiento no encontrado.", "warning")
            return redirigir_admin("establecimientos")

        nuevo_estado = 0 if int(establecimiento["activo"] or 0) == 1 else 1
        cursor.execute("""
            UPDATE establecimientos
            SET activo = ?, actualizado_por = ?, actualizado_en = ?
            WHERE id = ?
        """, (nuevo_estado, session.get("usuario_id"), fecha_actual(), establecimiento_id))

        registrar_auditoria(
            conexion,
            "Estado de establecimiento actualizado",
            "establecimiento",
            establecimiento_id,
            {"nombre": establecimiento["nombre"], "activo": nuevo_estado}
        )
        conexion.commit()
        flash("Establecimiento visible en el mapa." if nuevo_estado == 1 else "Establecimiento ocultado del mapa.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar estado del establecimiento:", error)
        flash("No se pudo cambiar el estado del establecimiento.", "error")
    finally:
        conexion.close()

    return redirigir_admin("establecimientos")

@app.route("/admin/manuales/guardar", methods=["POST"])
def admin_guardar_manual_vehiculo():

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
        registrar_auditoria(
            conexion,
            "Manual de modelo guardado",
            "vehiculo_modelo",
            modelo_id,
            {"origen": origen}
        )
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
def admin_cambiar_estado_manual(manual_id):

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
        registrar_auditoria(
            conexion,
            "Estado de manual actualizado",
            "manual_modelo",
            manual_id,
            {"activo": nuevo_estado, "origen": origen}
        )
        conexion.commit()
        flash("Manual activado." if nuevo_estado == 1 else "Manual ocultado.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al actualizar manual:", error)
        flash("No se pudo actualizar el manual.", "error")

    finally:
        conexion.close()

    return redirigir_operativo("manuales", origen)
