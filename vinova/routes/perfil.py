from vinova.core import *

@app.route("/perfil")
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

    notificaciones_usuario = listar_notificaciones_usuario(cursor, session["usuario_id"], limite=80)
    total_notificaciones_no_leidas = contar_notificaciones_usuario(
        cursor,
        session["usuario_id"],
        solo_no_leidas=True
    )

    conexion.close()

    ultimo_mantenimiento = historial_mantenimientos[0] if historial_mantenimientos else None
    proximo_mantenimiento = servicios_proximos[0] if servicios_proximos else None
    total_alertas = sum(1 for servicio in servicios_proximos if servicio.get("estado") == "vencido")

    def formato_km_resumen(valor):
        if valor is None:
            return ""
        return f"{int(valor):,}".replace(",", ".") + " km"

    proximo_resumen_valor = "Sin programar"
    proximo_resumen_detalle = "Registra un servicio"

    if proximo_mantenimiento:
        km_actual = normalizar_kilometraje(proximo_mantenimiento.get("kilometraje_actual"))
        km_proximo = normalizar_kilometraje(proximo_mantenimiento.get("proximo_kilometraje"))
        fecha_proxima = proximo_mantenimiento.get("proxima_fecha")

        if km_actual is not None and km_proximo is not None:
            km_restante = km_proximo - km_actual

            if km_restante <= 0:
                proximo_resumen_valor = "Vencido"
                proximo_resumen_detalle = f"Referencia: {formato_km_resumen(km_actual)}"
            else:
                proximo_resumen_valor = formato_km_resumen(km_restante)
                proximo_resumen_detalle = "Restantes"
        elif km_proximo is not None:
            proximo_resumen_valor = formato_km_resumen(km_proximo)
            proximo_resumen_detalle = "Kilometraje sugerido"
        elif fecha_proxima:
            proximo_resumen_valor = formatear_fecha_visible(fecha_proxima)
            proximo_resumen_detalle = "Fecha sugerida"
        else:
            proximo_resumen_valor = proximo_mantenimiento.get("estado_texto") or "Programado"
            proximo_resumen_detalle = "Próximo servicio"

    ultimo_resumen_valor = "Sin registros"
    ultimo_resumen_detalle = "Aún no disponible"

    if ultimo_mantenimiento:
        ultimo_resumen_valor = ultimo_mantenimiento.get("fecha_visible") or "Registrado"
        ultimo_resumen_detalle = f"{ultimo_mantenimiento.get('marca', '')} {ultimo_mantenimiento.get('modelo', '')} • {ultimo_mantenimiento.get('tipo_servicio', '')}".strip(" •")

    meses_abreviados = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    ahora_grafica = datetime.now()
    meses_grafica = []

    for desplazamiento in range(5, -1, -1):
        mes = ahora_grafica.month - desplazamiento
        anio = ahora_grafica.year

        while mes <= 0:
            mes += 12
            anio -= 1

        clave_mes = f"{anio:04d}-{mes:02d}"
        meses_grafica.append({
            "clave": clave_mes,
            "label": meses_abreviados[mes - 1]
        })

    conteo_grafica = {mes["clave"]: 0 for mes in meses_grafica}

    for mantenimiento in historial_mantenimientos:
        fecha_servicio_grafica = str(mantenimiento.get("fecha_servicio") or "")[:7]

        if fecha_servicio_grafica in conteo_grafica:
            conteo_grafica[fecha_servicio_grafica] += 1

    grafica_mantenimientos = {
        "labels": [mes["label"] for mes in meses_grafica],
        "values": [conteo_grafica[mes["clave"]] for mes in meses_grafica]
    }

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
        proximo_resumen_valor=proximo_resumen_valor,
        proximo_resumen_detalle=proximo_resumen_detalle,
        ultimo_resumen_valor=ultimo_resumen_valor,
        ultimo_resumen_detalle=ultimo_resumen_detalle,
        total_alertas_mantenimiento=total_alertas,
        grafica_mantenimientos=grafica_mantenimientos,
        manuales_usuario=manuales_usuario,
        facturas_usuario=facturas_usuario,
        preferencias_notificacion=preferencias_notificacion,
        notificaciones_usuario=notificaciones_usuario,
        total_notificaciones_no_leidas=total_notificaciones_no_leidas
    )


@app.route("/perfil/notificaciones/<int:notificacion_id>/leer", methods=["POST"])
def marcar_notificacion_leida(notificacion_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        asegurar_tabla_notificaciones_usuario(cursor)
        cursor.execute("""
            UPDATE notificaciones_usuario
            SET leida = 1,
                leida_en = COALESCE(leida_en, ?)
            WHERE id = ?
              AND usuario_id = ?
              AND COALESCE(eliminado_usuario, 0) = 0
        """, (
            fecha_actual(),
            notificacion_id,
            session["usuario_id"]
        ))
        conexion.commit()
        flash("Notificación marcada como leída.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al marcar notificación como leída:", error)
        flash("No se pudo actualizar la notificación.", "error")

    finally:
        conexion.close()

    return redirect("/perfil#seccion-notificaciones")


@app.route("/perfil/notificaciones/marcar-todas", methods=["POST"])
def marcar_todas_notificaciones_leidas():

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        asegurar_tabla_notificaciones_usuario(cursor)
        cursor.execute("""
            UPDATE notificaciones_usuario
            SET leida = 1,
                leida_en = COALESCE(leida_en, ?)
            WHERE usuario_id = ?
              AND COALESCE(leida, 0) = 0
              AND COALESCE(eliminado_usuario, 0) = 0
        """, (fecha_actual(), session["usuario_id"]))
        conexion.commit()
        flash("Todas las notificaciones fueron marcadas como leídas.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al marcar todas las notificaciones:", error)
        flash("No se pudieron actualizar las notificaciones.", "error")

    finally:
        conexion.close()

    return redirect("/perfil#seccion-notificaciones")


@app.route("/perfil/notificaciones/<int:notificacion_id>/ocultar", methods=["POST"])
def ocultar_notificacion_usuario(notificacion_id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        asegurar_tabla_notificaciones_usuario(cursor)
        cursor.execute("""
            UPDATE notificaciones_usuario
            SET eliminado_usuario = 1,
                leida = 1,
                leida_en = COALESCE(leida_en, ?)
            WHERE id = ?
              AND usuario_id = ?
        """, (
            fecha_actual(),
            notificacion_id,
            session["usuario_id"]
        ))
        conexion.commit()
        flash("Notificación ocultada de tu perfil.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al ocultar notificación:", error)
        flash("No se pudo ocultar la notificación.", "error")

    finally:
        conexion.close()

    return redirect("/perfil#seccion-notificaciones")


@app.route("/perfil/notificaciones", methods=["POST"])
def actualizar_preferencias_notificacion():

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
        registrar_auditoria(
            conexion,
            "Preferencias de notificación actualizadas",
            "usuario",
            session.get("usuario_id"),
            {
                "correo": notificar_correo,
                "mantenimientos": notificar_mantenimientos,
                "alertas": notificar_alertas,
                "facturas": notificar_facturas,
                "recordatorios": notificar_recordatorios
            }
        )
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
def registrar_mantenimiento():
    flash("Los mantenimientos de VINOVA son registrados por un trabajador autorizado.", "warning")
    return redirect("/perfil#seccion-historial")


@app.route("/perfil/mantenimiento/<int:mantenimiento_id>/eliminar", methods=["POST"])
def eliminar_mantenimiento(mantenimiento_id):
    flash("El historial de mantenimiento solo puede ser anulado por personal de VINOVA.", "warning")
    return redirect("/perfil#seccion-historial")


@app.route("/mantenimientos/buscar-vehiculos")
def buscar_vehiculos_mantenimiento():

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
def registrar_mantenimiento_empresarial():

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

        registrar_auditoria(
            conexion,
            "Mantenimiento registrado",
            "mantenimiento",
            mantenimiento_id,
            {
                "vehiculo_id": registro["vehiculo_id"],
                "usuario_id": registro["usuario_id"],
                "tipo_servicio": tipo_servicio,
                "factura_id": factura_id,
                "origen": origen
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
def anular_mantenimiento_empresarial(mantenimiento_id):

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

        registrar_auditoria(
            conexion,
            "Mantenimiento anulado",
            "mantenimiento",
            mantenimiento_id,
            {"motivo": motivo or "Anulado desde panel VINOVA", "origen": origen}
        )
        conexion.commit()
        flash("Mantenimiento anulado correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al anular mantenimiento:", error)
        flash("No se pudo anular el mantenimiento.", "error")

    finally:
        conexion.close()

    return redirect(destino)


@app.route("/perfil/vehiculo/agregar", methods=["POST"])
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

        registrar_auditoria(
            conexion,
            "Vehículo canjeado por cliente",
            "vehiculo",
            vehiculo_id,
            {"codigo": codigo_ingresado, "codigo_id": codigo["id"], "usuario_id": session.get("usuario_id")}
        )
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


@app.route("/perfil/foto", methods=["POST"])
def actualizar_foto_perfil():

    if "foto_perfil" not in request.files:
        flash("No seleccionaste ninguna imagen.", "warning")
        return redirect("/perfil")

    archivo = request.files["foto_perfil"]

    if archivo.filename == "":
        flash("No seleccionaste ninguna imagen.", "warning")
        return redirect("/perfil")

    if not extension_permitida(archivo.filename, EXTENSIONES_IMAGEN_VEHICULO):
        flash("Formato no permitido. Usa JPG, PNG o WEBP.", "warning")
        return redirect("/perfil")

    try:
        validar_archivo_imagen_real(archivo)

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

    registrar_auditoria(
        conexion,
        "Foto de perfil actualizada",
        "usuario",
        session.get("usuario_id"),
        {"proveedor": "Cloudinary"}
    )
    conexion.commit()
    conexion.close()

    session["foto_perfil"] = foto_url

    flash("Foto de perfil actualizada correctamente.", "success")
    return redirect("/perfil")
