from vinova.core import *

# =============================
# CATÁLOGO E INVENTARIO DE ARTÍCULOS
# =============================

ARTICULO_CATEGORIAS = [
    "Aceites",
    "Repuestos",
    "Filtros",
    "Baterías",
    "Llantas",
    "Accesorios",
    "Servicios",
    "Herramientas",
    "Otros",
]

ARTICULO_UNIDADES = ["Unidad", "Litro", "Galón", "Pieza", "Par", "Kit", "Servicio"]
ARTICULO_ESTADOS = ["Disponible", "Agotado", "Pedido", "No disponible"]

app.config.setdefault(
    "ARTICLE_IMAGE_FOLDER",
    os.path.join(BASE_DIR, "static", "img", "articulos")
)
os.makedirs(app.config["ARTICLE_IMAGE_FOLDER"], exist_ok=True)


def _rol_operativo():
    return str(session.get("rol", "")).upper() in {"ADMIN", "TRABAJADOR"}


def _origen_panel(origen=None):
    origen = (origen or request.form.get("origen") or request.args.get("origen") or "admin").strip().lower()
    return "trabajador" if origen == "trabajador" else "admin"


def _redirigir_articulos(origen=None):
    origen = _origen_panel(origen)
    if origen == "trabajador":
        return redirect(url_for("trabajador_panel") + "#trabajador-articulos")
    return redirect(url_for("admin_vehiculos") + "#admin-articulos")


def _guardar_imagen_articulo(archivo, codigo_articulo):
    if not archivo or not getattr(archivo, "filename", ""):
        return None

    if not extension_permitida(archivo.filename, EXTENSIONES_IMAGEN_VEHICULO):
        raise ValueError("Formato de imagen no permitido. Usa JPG, PNG o WEBP.")

    validar_archivo_imagen_real(archivo)
    extension = archivo.filename.rsplit(".", 1)[1].lower()
    nombre_archivo = secure_filename(
        f"{crear_slug(codigo_articulo or 'articulo')}-{int(time.time())}-{secrets.token_hex(4)}.{extension}"
    )
    ruta_absoluta = os.path.join(app.config["ARTICLE_IMAGE_FOLDER"], nombre_archivo)
    archivo.save(ruta_absoluta)
    return f"img/articulos/{nombre_archivo}"


def _generar_codigo_articulo(cursor, nombre, categoria="", articulo_id=None):
    base_categoria = crear_slug(categoria or "art")[:4].upper() or "ART"
    base_nombre = crear_slug(nombre or "producto")[:10].upper() or "PRODUCTO"
    candidato_base = f"ART-{base_categoria}-{base_nombre}"
    candidato = candidato_base
    contador = 1

    while True:
        if articulo_id:
            cursor.execute(
                "SELECT COUNT(*) FROM articulos WHERE UPPER(TRIM(codigo_articulo)) = UPPER(TRIM(?)) AND id != ?",
                (candidato, articulo_id),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM articulos WHERE UPPER(TRIM(codigo_articulo)) = UPPER(TRIM(?))",
                (candidato,),
            )

        if cursor.fetchone()[0] == 0:
            return candidato

        contador += 1
        candidato = f"{candidato_base}-{contador:02d}"


def _normalizar_stock(valor, defecto=0):
    numero = normalizar_precio(valor)
    if numero is None:
        return defecto
    return max(0, float(numero))


def _row_to_articulo(row, publico=False):
    articulo = dict(row)
    imagen = normalizar_ruta_static_documento(articulo.get("imagen"))
    articulo["imagen"] = imagen
    articulo["imagen_url"] = url_for("static", filename=imagen) if imagen else ""
    articulo["precio"] = normalizar_precio(articulo.get("precio")) or 0

    if not publico:
        articulo["costo"] = normalizar_precio(articulo.get("costo")) or 0
        articulo["stock"] = _normalizar_stock(articulo.get("stock"), 0)
        articulo["stock_minimo"] = _normalizar_stock(articulo.get("stock_minimo"), 0)
        articulo["unidades_vendidas"] = _normalizar_stock(articulo.get("unidades_vendidas"), 0)

    return articulo


def _consultar_articulos(cursor, *, incluir_archivados=False, solo_publicos=False):
    where = []
    params = []

    if not incluir_archivados:
        where.append("COALESCE(articulos.archivado, 0) = 0")

    if solo_publicos:
        where.append("COALESCE(articulos.activo, 1) = 1")
        where.append("COALESCE(articulos.archivado, 0) = 0")

    sql_where = "WHERE " + " AND ".join(where) if where else ""

    cursor.execute(f"""
        SELECT
            articulos.*,
            creador.nombre AS creado_por_nombre,
            actualizador.nombre AS actualizado_por_nombre
        FROM articulos
        LEFT JOIN usuarios AS creador
            ON creador.id = articulos.creado_por
        LEFT JOIN usuarios AS actualizador
            ON actualizador.id = articulos.actualizado_por
        {sql_where}
        ORDER BY COALESCE(articulos.archivado, 0), datetime(articulos.actualizado_en) DESC, articulos.id DESC
    """, params)

    return [_row_to_articulo(row, publico=solo_publicos) for row in cursor.fetchall()]


def _estadisticas_articulos(cursor):
    stats = {}

    consultas = {
        "total": "SELECT COUNT(*) FROM articulos WHERE COALESCE(archivado, 0) = 0",
        "activos": "SELECT COUNT(*) FROM articulos WHERE COALESCE(archivado, 0) = 0 AND COALESCE(activo, 1) = 1",
        "ocultos": "SELECT COUNT(*) FROM articulos WHERE COALESCE(archivado, 0) = 0 AND COALESCE(activo, 1) = 0",
        "bajo_stock": "SELECT COUNT(*) FROM articulos WHERE COALESCE(archivado, 0) = 0 AND COALESCE(stock, 0) <= COALESCE(stock_minimo, 0) AND COALESCE(stock_minimo, 0) > 0",
        "vendidos": "SELECT COALESCE(SUM(unidades_vendidas), 0) FROM articulos WHERE COALESCE(archivado, 0) = 0",
        "archivados": "SELECT COUNT(*) FROM articulos WHERE COALESCE(archivado, 0) = 1",
    }

    for clave, consulta in consultas.items():
        try:
            cursor.execute(consulta)
            stats[clave] = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError:
            stats[clave] = 0

    return stats


@app.route("/articulos")
def catalogo_articulos():
    """Catálogo público de artículos. No expone stock interno."""

    q = request.args.get("q", "").strip()
    categorias = [c for c in request.args.getlist("categoria") if c in ARTICULO_CATEGORIAS]
    marca = request.args.get("marca", "").strip()
    ordenar = request.args.get("ordenar", "recientes").strip()
    pagina = max(1, request.args.get("page", default=1, type=int) or 1)
    por_pagina = request.args.get("per_page", default=12, type=int) or 12
    por_pagina = min(max(por_pagina, 8), 36)

    filtros = ["COALESCE(archivado, 0) = 0", "COALESCE(activo, 1) = 1"]
    params = []

    if q:
        filtros.append("""
            (
                LOWER(nombre) LIKE LOWER(?)
                OR LOWER(codigo_articulo) LIKE LOWER(?)
                OR LOWER(marca) LIKE LOWER(?)
                OR LOWER(descripcion) LIKE LOWER(?)
            )
        """)
        term = f"%{q}%"
        params.extend([term, term, term, term])

    if categorias:
        filtros.append("categoria IN (" + ",".join("?" for _ in categorias) + ")")
        params.extend(categorias)

    if marca:
        filtros.append("LOWER(TRIM(marca)) = LOWER(TRIM(?))")
        params.append(marca)

    ordenes = {
        "recientes": "datetime(actualizado_en) DESC, id DESC",
        "precio_asc": "precio ASC, id DESC",
        "precio_desc": "precio DESC, id DESC",
        "nombre_asc": "nombre ASC",
        "categoria_asc": "categoria ASC, nombre ASC",
    }
    orden_sql = ordenes.get(ordenar, ordenes["recientes"])
    where_sql = "WHERE " + " AND ".join(filtros)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute(f"SELECT COUNT(*) FROM articulos {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(pagina, total_paginas)
        offset = (pagina - 1) * por_pagina

        cursor.execute(f"""
            SELECT id, codigo_articulo, nombre, categoria, marca, descripcion, imagen, precio, unidad, estado
            FROM articulos
            {where_sql}
            ORDER BY {orden_sql}
            LIMIT ? OFFSET ?
        """, params + [por_pagina, offset])
        articulos = [_row_to_articulo(row, publico=True) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT marca
            FROM articulos
            WHERE COALESCE(archivado, 0) = 0
              AND COALESCE(activo, 1) = 1
              AND TRIM(COALESCE(marca, '')) != ''
            ORDER BY marca ASC
        """)
        marcas = [row[0] for row in cursor.fetchall()]

        conteos_categoria = {}
        for categoria in ARTICULO_CATEGORIAS:
            cursor.execute("""
                SELECT COUNT(*)
                FROM articulos
                WHERE categoria = ?
                  AND COALESCE(archivado, 0) = 0
                  AND COALESCE(activo, 1) = 1
            """, (categoria,))
            conteos_categoria[categoria] = cursor.fetchone()[0] or 0

    except sqlite3.OperationalError:
        articulos = []
        marcas = []
        conteos_categoria = {categoria: 0 for categoria in ARTICULO_CATEGORIAS}
        total = 0
        total_paginas = 1
        flash("El catálogo de artículos aún no está migrado. Ejecuta la migración de artículos.", "warning")

    finally:
        conexion.close()

    return render_template(
        "articulos.html",
        articulos=articulos,
        categorias_articulo=ARTICULO_CATEGORIAS,
        marcas_articulo=marcas,
        conteos_categoria=conteos_categoria,
        q_actual=q,
        categorias_actuales=categorias,
        marca_actual=marca,
        orden_actual=ordenar,
        pagina_actual=pagina,
        per_page_actual=por_pagina,
        total_articulos=total,
        total_paginas=total_paginas,
    )


@app.route("/articulos/api/gestion")
def articulos_api_gestion():
    if not _rol_operativo():
        return jsonify({"ok": False, "error": "No autorizado."}), 403

    incluir_archivados = request.args.get("archivados") == "1"
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        articulos = _consultar_articulos(cursor, incluir_archivados=incluir_archivados)
        stats = _estadisticas_articulos(cursor)
        return jsonify({
            "ok": True,
            "articulos": articulos,
            "stats": stats,
            "categorias": ARTICULO_CATEGORIAS,
            "unidades": ARTICULO_UNIDADES,
            "estados": ARTICULO_ESTADOS,
        })
    except sqlite3.OperationalError as error:
        return jsonify({
            "ok": False,
            "error": "La tabla de artículos no existe. Ejecuta la migración.",
            "detalle": str(error),
            "articulos": [],
            "stats": _estadisticas_articulos(cursor),
        }), 500
    finally:
        conexion.close()


@app.route("/articulos/buscar-factura")
def buscar_articulos_factura():
    if not _rol_operativo():
        return jsonify({"ok": False, "error": "No autorizado.", "resultados": []}), 403

    q = request.args.get("q", "").strip()
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        params = []
        filtros = [
            "COALESCE(archivado, 0) = 0",
            "COALESCE(activo, 1) = 1",
            "COALESCE(stock, 0) > 0",
        ]

        if q:
            filtros.append("""
                (
                    LOWER(nombre) LIKE LOWER(?)
                    OR LOWER(codigo_articulo) LIKE LOWER(?)
                    OR LOWER(marca) LIKE LOWER(?)
                    OR LOWER(categoria) LIKE LOWER(?)
                )
            """)
            term = f"%{q}%"
            params.extend([term, term, term, term])

        cursor.execute(f"""
            SELECT id, codigo_articulo, nombre, categoria, marca, precio, stock, unidad, imagen
            FROM articulos
            WHERE {' AND '.join(filtros)}
            ORDER BY nombre ASC
            LIMIT 20
        """, params)

        resultados = [_row_to_articulo(row, publico=False) for row in cursor.fetchall()]
        return jsonify({"ok": True, "resultados": resultados})

    except sqlite3.OperationalError:
        return jsonify({"ok": False, "error": "Ejecuta la migración de artículos.", "resultados": []}), 500
    finally:
        conexion.close()


@app.route("/articulos/guardar", methods=["POST"])
def guardar_articulo():
    if not _rol_operativo():
        flash("No tienes permisos para gestionar artículos.", "warning")
        return redirect(url_for("inicio"))

    origen = _origen_panel()
    articulo_id = request.form.get("articulo_id", type=int)
    codigo_articulo = request.form.get("codigo_articulo", "").strip().upper()
    nombre = request.form.get("nombre", "").strip()
    categoria = request.form.get("categoria", "Otros").strip()
    marca = request.form.get("marca", "").strip()
    proveedor = request.form.get("proveedor", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    unidad = request.form.get("unidad", "Unidad").strip() or "Unidad"
    estado = request.form.get("estado", "Disponible").strip() or "Disponible"
    precio = normalizar_precio(request.form.get("precio"))
    costo = normalizar_precio(request.form.get("costo")) or 0
    stock = _normalizar_stock(request.form.get("stock"), 0)
    stock_minimo = _normalizar_stock(request.form.get("stock_minimo"), 0)
    activo = 1 if request.form.get("activo") == "on" else 0

    if categoria not in ARTICULO_CATEGORIAS:
        categoria = "Otros"

    if unidad not in ARTICULO_UNIDADES:
        unidad = "Unidad"

    if estado not in ARTICULO_ESTADOS:
        estado = "Disponible"

    if stock <= 0 and estado == "Disponible":
        estado = "Agotado"

    if not nombre:
        flash("El nombre del artículo es obligatorio.", "warning")
        return _redirigir_articulos(origen)

    if precio is None or precio < 0:
        flash("Ingresa un precio de venta válido.", "warning")
        return _redirigir_articulos(origen)

    imagen_file = request.files.get("imagen")
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()

        if not codigo_articulo:
            codigo_articulo = _generar_codigo_articulo(cursor, nombre, categoria, articulo_id)

        imagen_guardada = _guardar_imagen_articulo(imagen_file, codigo_articulo)

        if articulo_id:
            cursor.execute("SELECT * FROM articulos WHERE id = ? AND COALESCE(archivado, 0) = 0", (articulo_id,))
            actual = cursor.fetchone()

            if not actual:
                flash("El artículo no existe o fue archivado.", "warning")
                return _redirigir_articulos(origen)

            stock_anterior = _normalizar_stock(actual["stock"], 0)
            imagen_final = imagen_guardada or actual["imagen"] or ""

            cursor.execute("""
                UPDATE articulos
                SET codigo_articulo = ?, nombre = ?, categoria = ?, marca = ?, proveedor = ?, descripcion = ?,
                    imagen = ?, precio = ?, costo = ?, stock = ?, stock_minimo = ?, unidad = ?, estado = ?, activo = ?,
                    actualizado_por = ?, actualizado_en = ?
                WHERE id = ?
            """, (
                codigo_articulo, nombre, categoria, marca, proveedor, descripcion,
                imagen_final, precio, costo, stock, stock_minimo, unidad, estado, activo,
                session.get("usuario_id"), ahora, articulo_id,
            ))

            diferencia = stock - stock_anterior
            if abs(diferencia) > 0.0001:
                cursor.execute("""
                    INSERT INTO articulo_movimientos (
                        articulo_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo,
                        referencia_tipo, referencia_id, descripcion, creado_por, creado_en
                    )
                    VALUES (?, 'ajuste', ?, ?, ?, 'manual', NULL, ?, ?, ?)
                """, (
                    articulo_id,
                    diferencia,
                    stock_anterior,
                    stock,
                    "Ajuste manual de inventario",
                    session.get("usuario_id"),
                    ahora,
                ))

            accion = "Artículo actualizado"
            flash("Artículo actualizado correctamente.", "success")

        else:
            cursor.execute("""
                INSERT INTO articulos (
                    codigo_articulo, nombre, categoria, marca, proveedor, descripcion, imagen,
                    precio, costo, stock, stock_minimo, unidad, estado, activo,
                    unidades_vendidas, archivado, creado_por, actualizado_por, creado_en, actualizado_en
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
            """, (
                codigo_articulo, nombre, categoria, marca, proveedor, descripcion, imagen_guardada or "",
                precio, costo, stock, stock_minimo, unidad, estado, activo,
                session.get("usuario_id"), session.get("usuario_id"), ahora, ahora,
            ))
            articulo_id = cursor.lastrowid

            if stock > 0:
                cursor.execute("""
                    INSERT INTO articulo_movimientos (
                        articulo_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo,
                        referencia_tipo, referencia_id, descripcion, creado_por, creado_en
                    )
                    VALUES (?, 'entrada', ?, 0, ?, 'creacion', NULL, ?, ?, ?)
                """, (
                    articulo_id,
                    stock,
                    stock,
                    "Stock inicial al crear artículo",
                    session.get("usuario_id"),
                    ahora,
                ))

            accion = "Artículo creado"
            flash("Artículo agregado correctamente al inventario.", "success")

        registrar_auditoria(
            conexion,
            accion,
            "articulo",
            articulo_id,
            {"codigo": codigo_articulo, "nombre": nombre, "categoria": categoria, "stock": stock, "origen": origen},
        )
        conexion.commit()

    except sqlite3.IntegrityError:
        conexion.rollback()
        flash("Ya existe un artículo con ese código.", "warning")
    except ValueError as error:
        conexion.rollback()
        flash(str(error), "warning")
    except sqlite3.OperationalError as error:
        conexion.rollback()
        print("Error SQL al guardar artículo:", error)
        flash("No se pudo guardar. Ejecuta la migración de artículos.", "error")
    except Exception as error:
        conexion.rollback()
        print("Error al guardar artículo:", error)
        flash("No se pudo guardar el artículo.", "error")
    finally:
        conexion.close()

    return _redirigir_articulos(origen)


@app.route("/articulos/<int:articulo_id>/estado", methods=["POST"])
def cambiar_estado_articulo(articulo_id):
    if not _rol_operativo():
        return jsonify({"ok": False, "error": "No autorizado."}), 403

    origen = _origen_panel()
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id, nombre, COALESCE(activo, 1) AS activo, COALESCE(archivado, 0) AS archivado FROM articulos WHERE id = ?", (articulo_id,))
        articulo = cursor.fetchone()

        if not articulo or articulo["archivado"] == 1:
            return jsonify({"ok": False, "error": "Artículo no disponible."}), 404

        nuevo_estado = 0 if articulo["activo"] == 1 else 1
        cursor.execute("UPDATE articulos SET activo = ?, actualizado_por = ?, actualizado_en = ? WHERE id = ?", (nuevo_estado, session.get("usuario_id"), fecha_actual(), articulo_id))
        registrar_auditoria(conexion, "Estado de artículo actualizado", "articulo", articulo_id, {"activo": nuevo_estado, "origen": origen})
        conexion.commit()
        return jsonify({"ok": True, "activo": nuevo_estado})

    except Exception as error:
        conexion.rollback()
        print("Error al cambiar estado de artículo:", error)
        return jsonify({"ok": False, "error": "No se pudo actualizar el artículo."}), 500
    finally:
        conexion.close()


@app.route("/articulos/<int:articulo_id>/archivar", methods=["POST"])
def archivar_articulo(articulo_id):
    if not _rol_operativo():
        return jsonify({"ok": False, "error": "No autorizado."}), 403

    origen = _origen_panel()
    motivo = request.form.get("motivo", "").strip() or "Archivado desde inventario de artículos"
    ahora = fecha_actual()
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id, nombre, COALESCE(archivado, 0) AS archivado FROM articulos WHERE id = ?", (articulo_id,))
        articulo = cursor.fetchone()

        if not articulo:
            return jsonify({"ok": False, "error": "Artículo no encontrado."}), 404

        cursor.execute("""
            UPDATE articulos
            SET archivado = 1, activo = 0, archivado_por = ?, archivado_en = ?, motivo_archivado = ?, actualizado_por = ?, actualizado_en = ?
            WHERE id = ?
        """, (session.get("usuario_id"), ahora, motivo, session.get("usuario_id"), ahora, articulo_id))

        registrar_auditoria(conexion, "Artículo archivado", "articulo", articulo_id, {"motivo": motivo, "origen": origen})
        conexion.commit()
        return jsonify({"ok": True})

    except Exception as error:
        conexion.rollback()
        print("Error al archivar artículo:", error)
        return jsonify({"ok": False, "error": "No se pudo archivar el artículo."}), 500
    finally:
        conexion.close()


@app.route("/admin/vehiculos/ocultos/api")
@app.route("/inventario/vehiculos/ocultos/api")
def admin_vehiculos_ocultos_api():
    if not _rol_operativo():
        return jsonify({"ok": False, "error": "No autorizado."}), 403

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, codigo_catalogo, marca, modelo, anio, tipo_vehiculo, combustible, transmision,
                   kilometraje, precio, imagen, descripcion, estado, activo, actualizado_en
            FROM vehiculos
            WHERE COALESCE(archivado, 0) = 0
              AND COALESCE(activo, 0) = 0
              AND COALESCE(NULLIF(TRIM(estado), ''), 'Disponible') != 'Vendido'
            ORDER BY datetime(actualizado_en) DESC, id DESC
        """)
        vehiculos = []
        for row in cursor.fetchall():
            vehiculo = dict(row)
            imagen = normalizar_ruta_static_documento(vehiculo.get("imagen"))
            vehiculo["imagen"] = imagen
            vehiculo["imagen_url"] = url_for("static", filename=imagen) if imagen else ""
            vehiculo["precio"] = normalizar_precio(vehiculo.get("precio")) or 0
            vehiculo["kilometraje"] = normalizar_kilometraje(vehiculo.get("kilometraje")) or 0
            vehiculos.append(vehiculo)

        return jsonify({"ok": True, "vehiculos": vehiculos, "total": len(vehiculos)})

    finally:
        conexion.close()

@app.route("/inventario/vehiculos/<int:vehiculo_id>/activar", methods=["POST"])
def activar_vehiculo_oculto(vehiculo_id):
    if not _rol_operativo():
        flash("No tienes permisos para activar vehículos.", "warning")
        return redirect(url_for("inicio"))

    origen = _origen_panel()
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, marca, modelo, estado, COALESCE(archivado, 0) AS archivado
            FROM vehiculos
            WHERE id = ?
        """, (vehiculo_id,))
        vehiculo = cursor.fetchone()

        if not vehiculo:
            flash("Vehículo no encontrado.", "warning")
        elif vehiculo["archivado"] == 1:
            flash("No puedes activar un vehículo archivado desde inventario oculto.", "warning")
        elif vehiculo["estado"] == "Vendido":
            flash("No puedes activar un vehículo vendido.", "warning")
        else:
            cursor.execute("""
                UPDATE vehiculos
                SET activo = 1, actualizado_en = ?
                WHERE id = ?
            """, (fecha_actual(), vehiculo_id))
            registrar_auditoria(
                conexion,
                "Vehículo activado desde inventario oculto",
                "vehiculo",
                vehiculo_id,
                {"origen": origen, "activo": 1},
            )
            conexion.commit()
            flash("Vehículo activado en el catálogo público.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al activar vehículo oculto:", error)
        flash("No se pudo activar el vehículo.", "error")
    finally:
        conexion.close()

    if origen == "trabajador":
        return redirect(url_for("trabajador_panel") + "#trabajador-ocultos")
    return redirect(url_for("admin_vehiculos") + "#admin-ocultos")

