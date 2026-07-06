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



def _telefono_whatsapp_url(telefono, mensaje):
    numero = solo_digitos(telefono or "")
    if not numero:
        return ""
    if numero.startswith("0"):
        numero = "593" + numero[1:]
    from urllib.parse import quote
    return f"https://wa.me/{numero}?text={quote(mensaje or '')}"


def _establecimientos_activos(cursor):
    try:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE COALESCE(activo, 1) = 1
            ORDER BY COALESCE(distancia_km, 999999) ASC, nombre ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []


def _concesionarias_activas(cursor):
    try:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE COALESCE(activo, 1) = 1
              AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
            ORDER BY COALESCE(distancia_km, 999999) ASC, nombre ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []


def _establecimiento_usuario_actual(cursor):
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None

    try:
        cursor.execute("""
            SELECT id, establecimiento, establecimiento_id
            FROM usuarios
            WHERE id = ?
        """, (usuario_id,))
        usuario = cursor.fetchone()
    except sqlite3.OperationalError:
        cursor.execute("SELECT id, establecimiento FROM usuarios WHERE id = ?", (usuario_id,))
        usuario = cursor.fetchone()

    if not usuario:
        return None

    try:
        establecimiento_id = usuario["establecimiento_id"]
    except Exception:
        establecimiento_id = None

    if establecimiento_id:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE id = ? AND COALESCE(activo, 1) = 1
        """, (establecimiento_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)

    nombre = (usuario["establecimiento"] or "").strip() if "establecimiento" in usuario.keys() else ""
    if nombre:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?)) AND COALESCE(activo, 1) = 1
            LIMIT 1
        """, (nombre,))
        row = cursor.fetchone()
        if row:
            return dict(row)

    return None


def _establecimiento_operativo(cursor):
    rol = str(session.get("rol", "")).upper()
    solicitado = request.form.get("establecimiento_id", type=int) or request.args.get("establecimiento_id", type=int)

    if rol == "ADMIN" and solicitado:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE id = ? AND COALESCE(activo, 1) = 1
        """, (solicitado,))
        row = cursor.fetchone()
        if row:
            return dict(row)

    solicitado_nombre = request.form.get("establecimiento", "").strip() or request.args.get("establecimiento", "").strip()
    if rol == "ADMIN" and solicitado_nombre:
        cursor.execute("""
            SELECT id, nombre, tipo, direccion, ciudad, provincia, telefono, lat, lng, distancia_km
            FROM establecimientos
            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?)) AND COALESCE(activo, 1) = 1
            LIMIT 1
        """, (solicitado_nombre,))
        row = cursor.fetchone()
        if row:
            return dict(row)

    asignado = _establecimiento_usuario_actual(cursor)
    if asignado:
        return asignado

    activos = _establecimientos_activos(cursor)
    return activos[0] if activos else None


def _asegurar_stock_establecimiento(cursor, articulo_id, establecimiento_id, stock=0, stock_minimo=0):
    if not establecimiento_id:
        return
    ahora = fecha_actual()
    cursor.execute("""
        INSERT INTO articulo_stock_establecimiento (
            articulo_id, establecimiento_id, stock, stock_minimo, unidades_vendidas, creado_en, actualizado_en
        )
        VALUES (?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(articulo_id, establecimiento_id)
        DO UPDATE SET stock = excluded.stock,
                      stock_minimo = excluded.stock_minimo,
                      actualizado_en = excluded.actualizado_en
    """, (articulo_id, establecimiento_id, stock, stock_minimo, ahora, ahora))


def _stock_establecimiento_actual(cursor, articulo_id, establecimiento_id):
    if not establecimiento_id:
        return 0
    try:
        cursor.execute("""
            SELECT COALESCE(stock, 0) AS stock
            FROM articulo_stock_establecimiento
            WHERE articulo_id = ? AND establecimiento_id = ?
            LIMIT 1
        """, (articulo_id, establecimiento_id))
        row = cursor.fetchone()
        return _normalizar_stock(row["stock"] if row else 0, 0)
    except sqlite3.OperationalError:
        return 0


def _stock_minimo_establecimiento_actual(cursor, articulo_id, establecimiento_id):
    if not establecimiento_id:
        return 0
    try:
        cursor.execute("""
            SELECT COALESCE(stock_minimo, 0) AS stock_minimo
            FROM articulo_stock_establecimiento
            WHERE articulo_id = ? AND establecimiento_id = ?
            LIMIT 1
        """, (articulo_id, establecimiento_id))
        row = cursor.fetchone()
        return _normalizar_stock(row["stock_minimo"] if row else 0, 0)
    except sqlite3.OperationalError:
        return 0


def _registrar_movimiento_articulo(
    cursor,
    *,
    articulo_id,
    tipo_movimiento,
    cantidad,
    stock_anterior,
    stock_nuevo,
    referencia_tipo="manual",
    referencia_id=None,
    descripcion="",
    establecimiento_id=None,
):
    ahora = fecha_actual()
    try:
        cursor.execute("""
            INSERT INTO articulo_movimientos (
                articulo_id, establecimiento_id, tipo_movimiento, cantidad,
                stock_anterior, stock_nuevo, referencia_tipo, referencia_id,
                descripcion, creado_por, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            articulo_id,
            establecimiento_id,
            tipo_movimiento,
            cantidad,
            stock_anterior,
            stock_nuevo,
            referencia_tipo,
            referencia_id,
            descripcion,
            session.get("usuario_id"),
            ahora,
        ))
    except sqlite3.OperationalError:
        cursor.execute("""
            INSERT INTO articulo_movimientos (
                articulo_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo,
                referencia_tipo, referencia_id, descripcion, creado_por, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            articulo_id,
            tipo_movimiento,
            cantidad,
            stock_anterior,
            stock_nuevo,
            referencia_tipo,
            referencia_id,
            descripcion,
            session.get("usuario_id"),
            ahora,
        ))


def _recalcular_stock_articulo(cursor, articulo_id):
    try:
        cursor.execute("""
            SELECT
                COALESCE(SUM(stock), 0) AS stock_total,
                COALESCE(SUM(unidades_vendidas), 0) AS vendidas_total,
                COALESCE(MAX(stock_minimo), 0) AS stock_minimo_ref
            FROM articulo_stock_establecimiento
            WHERE articulo_id = ?
        """, (articulo_id,))
        row = cursor.fetchone()
        stock_total = normalizar_precio(row["stock_total"] if row else 0) or 0
        vendidas_total = normalizar_precio(row["vendidas_total"] if row else 0) or 0
        stock_minimo_ref = normalizar_precio(row["stock_minimo_ref"] if row else 0) or 0
        cursor.execute("""
            UPDATE articulos
            SET stock = ?,
                unidades_vendidas = ?,
                stock_minimo = CASE WHEN COALESCE(stock_minimo, 0) = 0 THEN ? ELSE stock_minimo END,
                estado = CASE WHEN ? <= 0 THEN 'Agotado' ELSE 'Disponible' END,
                actualizado_en = ?
            WHERE id = ?
        """, (stock_total, vendidas_total, stock_minimo_ref, stock_total, fecha_actual(), articulo_id))
    except sqlite3.OperationalError:
        return


def _stock_por_establecimiento(cursor, articulo_id, solo_concesionarias=False):
    filtro_tipo = ""
    if solo_concesionarias:
        filtro_tipo = "AND LOWER(TRIM(COALESCE(establecimientos.tipo, ''))) = 'concesionario'"

    try:
        cursor.execute(f"""
            SELECT
                ase.establecimiento_id,
                establecimientos.nombre,
                establecimientos.direccion,
                establecimientos.ciudad,
                establecimientos.telefono,
                establecimientos.lat,
                establecimientos.lng,
                COALESCE(establecimientos.distancia_km, 999999) AS distancia_km,
                COALESCE(ase.stock, 0) AS stock,
                COALESCE(ase.stock_minimo, 0) AS stock_minimo,
                COALESCE(ase.unidades_vendidas, 0) AS unidades_vendidas
            FROM articulo_stock_establecimiento AS ase
            INNER JOIN establecimientos
                ON establecimientos.id = ase.establecimiento_id
            WHERE ase.articulo_id = ?
              AND COALESCE(establecimientos.activo, 1) = 1
              {filtro_tipo}
            ORDER BY COALESCE(establecimientos.distancia_km, 999999) ASC, establecimientos.nombre ASC
        """, (articulo_id,))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []


def _stock_establecimientos_desde_form(cursor):
    if str(session.get("rol", "")).upper() != "ADMIN":
        return None

    establecimientos = _concesionarias_activas(cursor)
    if not establecimientos:
        return None

    stock_por_sucursal = {}
    recibio_stock_por_sucursal = False

    for establecimiento in establecimientos:
        establecimiento_id = establecimiento.get("id")
        if not establecimiento_id:
            continue

        stock_key = f"stock_establecimiento_{establecimiento_id}"
        minimo_key = f"stock_minimo_establecimiento_{establecimiento_id}"

        if stock_key not in request.form and minimo_key not in request.form:
            continue

        recibio_stock_por_sucursal = True
        stock_por_sucursal[int(establecimiento_id)] = {
            "stock": _normalizar_stock(request.form.get(stock_key), 0),
            "stock_minimo": _normalizar_stock(request.form.get(minimo_key), 0),
        }

    return stock_por_sucursal if recibio_stock_por_sucursal else None


def _enriquecer_disponibilidad_publica(cursor, articulos):
    instituciones_url = url_for("instituciones")

    for articulo in articulos:
        filas_stock = _stock_por_establecimiento(cursor, articulo["id"], solo_concesionarias=True)
        disponibles = []
        for fila in filas_stock:
            stock = normalizar_precio(fila.get("stock")) or 0
            if stock > 0:
                disponibles.append(fila)

        cantidad = len(disponibles)
        articulo["disponible_sucursales"] = cantidad
        articulo["instituciones_url"] = instituciones_url
        articulo["sucursales_disponibles"] = []

        if cantidad <= 0:
            articulo["disponibilidad_estado"] = "agotado"
            articulo["disponibilidad_label"] = "Agotado temporalmente"
            articulo["disponibilidad_detalle"] = "Consulta instituciones para ubicar el local más cercano o pregunta por reposición."
            articulo["whatsapp_url"] = ""
            continue

        if cantidad > 1:
            articulo["disponibilidad_estado"] = "total"
            articulo["disponibilidad_label"] = "Disponible en tu VINOVA más cercano"
            articulo["disponibilidad_detalle"] = f"Disponible en {cantidad} sucursales VINOVA. Te mostramos primero la más cercana registrada."
            sucursales_para_mostrar = disponibles
        elif cantidad == 1:
            articulo["disponibilidad_estado"] = "parcial"
            articulo["disponibilidad_label"] = "Disponible en 1 sucursal"
            articulo["disponibilidad_detalle"] = "Disponible en una sucursal VINOVA. Puedes reservarlo por WhatsApp."
            sucursales_para_mostrar = disponibles[:1]
        else:
            articulo["disponibilidad_estado"] = "parcial"
            articulo["disponibilidad_label"] = f"Disponible en {cantidad} sucursales"
            articulo["disponibilidad_detalle"] = "Elige una sucursal disponible al reservar por WhatsApp."
            sucursales_para_mostrar = disponibles

        for sucursal in sucursales_para_mostrar:
            mensaje = (
                f"Hola VINOVA, quiero reservar el artículo {articulo.get('nombre', '')} "
                f"({articulo.get('codigo_articulo', 'sin código')}) en {sucursal.get('nombre', 'VINOVA')}."
            )
            articulo["sucursales_disponibles"].append({
                "id": sucursal.get("establecimiento_id"),
                "nombre": sucursal.get("nombre") or "VINOVA",
                "direccion": sucursal.get("direccion") or "Dirección no registrada",
                "ciudad": sucursal.get("ciudad") or "",
                "telefono": sucursal.get("telefono") or "",
                "whatsapp_url": _telefono_whatsapp_url(sucursal.get("telefono"), mensaje),
            })

        articulo["whatsapp_url"] = articulo["sucursales_disponibles"][0].get("whatsapp_url") if articulo["sucursales_disponibles"] else ""

    return articulos


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


def _movimientos_recientes_articulo(cursor, articulo_id, limite=6):
    try:
        cursor.execute("""
            SELECT
                movimientos.id,
                movimientos.tipo_movimiento,
                movimientos.cantidad,
                movimientos.stock_anterior,
                movimientos.stock_nuevo,
                movimientos.referencia_tipo,
                movimientos.referencia_id,
                movimientos.descripcion,
                movimientos.creado_en,
                establecimientos.nombre AS establecimiento_nombre,
                usuarios.nombre AS creado_por_nombre
            FROM articulo_movimientos AS movimientos
            LEFT JOIN establecimientos
                ON establecimientos.id = movimientos.establecimiento_id
            LEFT JOIN usuarios
                ON usuarios.id = movimientos.creado_por
            WHERE movimientos.articulo_id = ?
            ORDER BY datetime(movimientos.creado_en) DESC, movimientos.id DESC
            LIMIT ?
        """, (articulo_id, limite))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []


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
        articulos = _enriquecer_disponibilidad_publica(cursor, articulos)

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
        for articulo in articulos:
            articulo["stock_establecimientos"] = _stock_por_establecimiento(cursor, articulo["id"], solo_concesionarias=True)
            articulo["movimientos_recientes"] = _movimientos_recientes_articulo(cursor, articulo["id"])
        stats = _estadisticas_articulos(cursor)
        return jsonify({
            "ok": True,
            "articulos": articulos,
            "stats": stats,
            "categorias": ARTICULO_CATEGORIAS,
            "unidades": ARTICULO_UNIDADES,
            "estados": ARTICULO_ESTADOS,
            "establecimientos": _establecimientos_activos(cursor),
            "establecimiento_actual": _establecimiento_operativo(cursor),
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
        establecimiento = _establecimiento_operativo(cursor)
        establecimiento_id = establecimiento.get("id") if establecimiento else None
        params = []
        filtros = [
            "COALESCE(articulos.archivado, 0) = 0",
            "COALESCE(articulos.activo, 1) = 1",
        ]

        join_stock = ""
        select_stock = "COALESCE(articulos.stock, 0) AS stock"
        if establecimiento_id:
            join_stock = """
                INNER JOIN articulo_stock_establecimiento AS ase
                    ON ase.articulo_id = articulos.id
                   AND ase.establecimiento_id = ?
                   AND COALESCE(ase.stock, 0) > 0
            """
            params.append(establecimiento_id)
            select_stock = "COALESCE(ase.stock, 0) AS stock"
        else:
            filtros.append("COALESCE(articulos.stock, 0) > 0")

        if q:
            filtros.append("""
                (
                    LOWER(articulos.nombre) LIKE LOWER(?)
                    OR LOWER(articulos.codigo_articulo) LIKE LOWER(?)
                    OR LOWER(articulos.marca) LIKE LOWER(?)
                    OR LOWER(articulos.categoria) LIKE LOWER(?)
                )
            """)
            term = f"%{q}%"
            params.extend([term, term, term, term])

        cursor.execute(f"""
            SELECT articulos.id, articulos.codigo_articulo, articulos.nombre, articulos.categoria,
                   articulos.marca, articulos.precio, {select_stock}, articulos.unidad, articulos.imagen
            FROM articulos
            {join_stock}
            WHERE {' AND '.join(filtros)}
            ORDER BY articulos.nombre ASC
            LIMIT 20
        """, params)

        resultados = [_row_to_articulo(row, publico=False) for row in cursor.fetchall()]
        return jsonify({"ok": True, "resultados": resultados, "establecimiento": establecimiento})

    except sqlite3.OperationalError as error:
        return jsonify({"ok": False, "error": "Ejecuta la migración de inventario por establecimiento.", "detalle": str(error), "resultados": []}), 500
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
    estado_solicitado = estado
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
    imagen_existente = normalizar_ruta_static_documento(request.form.get("imagen_existente", ""))
    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        ahora = fecha_actual()
        establecimiento_operativo = _establecimiento_operativo(cursor)
        establecimiento_id = establecimiento_operativo.get("id") if establecimiento_operativo else None
        stock_por_sucursal = _stock_establecimientos_desde_form(cursor)

        if stock_por_sucursal is not None:
            stock = sum(item["stock"] for item in stock_por_sucursal.values())
            stock_minimo = max([item["stock_minimo"] for item in stock_por_sucursal.values()] or [0])

        if stock <= 0 and estado == "Disponible":
            estado = "Agotado"
        elif stock > 0 and estado == "Agotado" and estado_solicitado == "Disponible":
            estado = "Disponible"

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
            imagen_final = imagen_guardada or imagen_existente or actual["imagen"] or ""
            movimiento_registrado = False

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

            if imagen_final != (actual["imagen"] or ""):
                eliminar_archivo_static_si_no_referenciado(cursor, actual["imagen"])

            if stock_por_sucursal is not None:
                for sucursal_id, valores_stock in stock_por_sucursal.items():
                    stock_anterior_est = _stock_establecimiento_actual(cursor, articulo_id, sucursal_id)
                    _asegurar_stock_establecimiento(
                        cursor,
                        articulo_id,
                        sucursal_id,
                        valores_stock["stock"],
                        valores_stock["stock_minimo"],
                    )
                    diferencia_est = valores_stock["stock"] - stock_anterior_est
                    if abs(diferencia_est) > 0.0001:
                        _registrar_movimiento_articulo(
                            cursor,
                            articulo_id=articulo_id,
                            establecimiento_id=sucursal_id,
                            tipo_movimiento="ajuste",
                            cantidad=diferencia_est,
                            stock_anterior=stock_anterior_est,
                            stock_nuevo=valores_stock["stock"],
                            referencia_tipo="manual",
                            descripcion="Ajuste manual de inventario por concesionaria",
                        )
                        movimiento_registrado = True
                _recalcular_stock_articulo(cursor, articulo_id)
            elif establecimiento_id:
                filas_actuales = _stock_por_establecimiento(cursor, articulo_id)
                stock_anterior_est = 0
                for fila_stock in filas_actuales:
                    if int(fila_stock.get("establecimiento_id") or 0) == int(establecimiento_id):
                        stock_anterior_est = _normalizar_stock(fila_stock.get("stock"), 0)
                        break
                _asegurar_stock_establecimiento(cursor, articulo_id, establecimiento_id, stock, stock_minimo)
                _recalcular_stock_articulo(cursor, articulo_id)
                stock_anterior = stock_anterior_est
                diferencia_est = stock - stock_anterior_est
                if abs(diferencia_est) > 0.0001:
                    _registrar_movimiento_articulo(
                        cursor,
                        articulo_id=articulo_id,
                        establecimiento_id=establecimiento_id,
                        tipo_movimiento="ajuste",
                        cantidad=diferencia_est,
                        stock_anterior=stock_anterior_est,
                        stock_nuevo=stock,
                        referencia_tipo="manual",
                        descripcion="Ajuste manual de inventario",
                    )
                    movimiento_registrado = True
            diferencia = stock - stock_anterior
            if abs(diferencia) > 0.0001 and not movimiento_registrado:
                _registrar_movimiento_articulo(
                    cursor,
                    articulo_id=articulo_id,
                    tipo_movimiento="ajuste",
                    cantidad=diferencia,
                    stock_anterior=stock_anterior,
                    stock_nuevo=stock,
                    referencia_tipo="manual",
                    descripcion="Ajuste manual de inventario",
                )

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
                codigo_articulo, nombre, categoria, marca, proveedor, descripcion, imagen_guardada or imagen_existente or "",
                precio, costo, stock, stock_minimo, unidad, estado, activo,
                session.get("usuario_id"), session.get("usuario_id"), ahora, ahora,
            ))
            articulo_id = cursor.lastrowid

            if stock_por_sucursal is not None:
                for sucursal_id, valores_stock in stock_por_sucursal.items():
                    _asegurar_stock_establecimiento(
                        cursor,
                        articulo_id,
                        sucursal_id,
                        valores_stock["stock"],
                        valores_stock["stock_minimo"],
                    )
                    if valores_stock["stock"] > 0:
                        _registrar_movimiento_articulo(
                            cursor,
                            articulo_id=articulo_id,
                            establecimiento_id=sucursal_id,
                            tipo_movimiento="entrada",
                            cantidad=valores_stock["stock"],
                            stock_anterior=0,
                            stock_nuevo=valores_stock["stock"],
                            referencia_tipo="creacion",
                            descripcion="Stock inicial al crear artículo por concesionaria",
                        )
                _recalcular_stock_articulo(cursor, articulo_id)
            elif establecimiento_id:
                _asegurar_stock_establecimiento(cursor, articulo_id, establecimiento_id, stock, stock_minimo)
                _recalcular_stock_articulo(cursor, articulo_id)
                if stock > 0:
                    _registrar_movimiento_articulo(
                        cursor,
                        articulo_id=articulo_id,
                        establecimiento_id=establecimiento_id,
                        tipo_movimiento="entrada",
                        cantidad=stock,
                        stock_anterior=0,
                        stock_nuevo=stock,
                        referencia_tipo="creacion",
                        descripcion="Stock inicial al crear artículo",
                    )
            elif stock > 0:
                _registrar_movimiento_articulo(
                    cursor,
                    articulo_id=articulo_id,
                    tipo_movimiento="entrada",
                    cantidad=stock,
                    stock_anterior=0,
                    stock_nuevo=stock,
                    referencia_tipo="creacion",
                    descripcion="Stock inicial al crear artículo",
                )

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


@app.route("/articulos/transferir-stock", methods=["POST"])
def transferir_stock_articulo():
    if str(session.get("rol", "")).upper() != "ADMIN":
        flash("Solo administración puede transferir stock entre concesionarias.", "warning")
        return redirect(url_for("inicio"))

    origen_panel = _origen_panel()
    articulo_id = request.form.get("articulo_id", type=int)
    origen_id = request.form.get("origen_id", type=int)
    destino_id = request.form.get("destino_id", type=int)
    cantidad = _normalizar_stock(request.form.get("cantidad"), 0)
    motivo = request.form.get("motivo", "").strip() or "Transferencia de stock entre concesionarias"

    if not articulo_id or not origen_id or not destino_id:
        flash("Selecciona artículo, concesionaria origen y concesionaria destino.", "warning")
        return _redirigir_articulos(origen_panel)

    if origen_id == destino_id:
        flash("La concesionaria origen y destino deben ser diferentes.", "warning")
        return _redirigir_articulos(origen_panel)

    if cantidad <= 0:
        flash("Ingresa una cantidad válida para transferir.", "warning")
        return _redirigir_articulos(origen_panel)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            SELECT id, nombre, unidad, COALESCE(archivado, 0) AS archivado
            FROM articulos
            WHERE id = ?
            LIMIT 1
        """, (articulo_id,))
        articulo = cursor.fetchone()
        if not articulo or articulo["archivado"] == 1:
            raise ValueError("El artículo no existe o fue archivado.")

        concesionarias = {
            item["id"]: item
            for item in _concesionarias_activas(cursor)
            if item.get("id") in {origen_id, destino_id}
        }
        if origen_id not in concesionarias or destino_id not in concesionarias:
            raise ValueError("Origen y destino deben ser concesionarias activas.")

        stock_origen = _stock_establecimiento_actual(cursor, articulo_id, origen_id)
        if cantidad > stock_origen:
            unidad = articulo["unidad"] or "Unidad"
            raise ValueError(f"Stock insuficiente en {concesionarias[origen_id]['nombre']}. Disponible: {stock_origen:g} {unidad}.")

        stock_destino = _stock_establecimiento_actual(cursor, articulo_id, destino_id)
        minimo_origen = _stock_minimo_establecimiento_actual(cursor, articulo_id, origen_id)
        minimo_destino = _stock_minimo_establecimiento_actual(cursor, articulo_id, destino_id)
        nuevo_origen = stock_origen - cantidad
        nuevo_destino = stock_destino + cantidad

        _asegurar_stock_establecimiento(cursor, articulo_id, origen_id, nuevo_origen, minimo_origen)
        _asegurar_stock_establecimiento(cursor, articulo_id, destino_id, nuevo_destino, minimo_destino)

        descripcion = (
            f"{motivo}: {concesionarias[origen_id]['nombre']} -> "
            f"{concesionarias[destino_id]['nombre']}"
        )
        _registrar_movimiento_articulo(
            cursor,
            articulo_id=articulo_id,
            establecimiento_id=origen_id,
            tipo_movimiento="transferencia_salida",
            cantidad=-cantidad,
            stock_anterior=stock_origen,
            stock_nuevo=nuevo_origen,
            referencia_tipo="transferencia",
            descripcion=descripcion,
        )
        _registrar_movimiento_articulo(
            cursor,
            articulo_id=articulo_id,
            establecimiento_id=destino_id,
            tipo_movimiento="transferencia_entrada",
            cantidad=cantidad,
            stock_anterior=stock_destino,
            stock_nuevo=nuevo_destino,
            referencia_tipo="transferencia",
            descripcion=descripcion,
        )

        _recalcular_stock_articulo(cursor, articulo_id)
        registrar_auditoria(
            conexion,
            "Stock de artículo transferido",
            "articulo",
            articulo_id,
            {
                "origen_id": origen_id,
                "destino_id": destino_id,
                "cantidad": cantidad,
                "motivo": motivo,
            },
        )
        conexion.commit()
        flash("Stock transferido correctamente entre concesionarias.", "success")

    except ValueError as error:
        conexion.rollback()
        flash(str(error), "warning")
    except Exception as error:
        conexion.rollback()
        print("Error al transferir stock:", error)
        flash("No se pudo transferir el stock.", "error")
    finally:
        conexion.close()

    return _redirigir_articulos(origen_panel)


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


@app.route("/admin/articulos/<int:articulo_id>/eliminar-permanente", methods=["POST"])
def eliminar_articulo_permanente(articulo_id):
    """Elimina definitivamente un artículo archivado y limpia imagen local no compartida."""

    if str(session.get("rol", "")).upper() != "ADMIN":
        return jsonify({"ok": False, "error": "Solo un administrador puede eliminar permanentemente."}), 403

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            SELECT *, COALESCE(archivado, 0) AS archivado_normalizado
            FROM articulos
            WHERE id = ?
        """, (articulo_id,))
        articulo = cursor.fetchone()

        if not articulo:
            conexion.rollback()
            return jsonify({"ok": False, "error": "Artículo no encontrado."}), 404

        if articulo["archivado_normalizado"] != 1:
            conexion.rollback()
            return jsonify({"ok": False, "error": "Solo puedes eliminar permanentemente artículos archivados."}), 400

        imagen_articulo = normalizar_ruta_static_documento(articulo["imagen"] if "imagen" in articulo.keys() else "")

        if tabla_existe_db(cursor, "factura_articulos") and columna_existe_db(cursor, "factura_articulos", "articulo_id"):
            cursor.execute("DELETE FROM factura_articulos WHERE articulo_id = ?", (articulo_id,))

        if tabla_existe_db(cursor, "articulo_stock_establecimiento") and columna_existe_db(cursor, "articulo_stock_establecimiento", "articulo_id"):
            cursor.execute("DELETE FROM articulo_stock_establecimiento WHERE articulo_id = ?", (articulo_id,))

        if tabla_existe_db(cursor, "articulo_movimientos") and columna_existe_db(cursor, "articulo_movimientos", "articulo_id"):
            cursor.execute("DELETE FROM articulo_movimientos WHERE articulo_id = ?", (articulo_id,))

        cursor.execute("DELETE FROM articulos WHERE id = ?", (articulo_id,))

        archivo_borrado = False
        if imagen_articulo:
            archivo_borrado = eliminar_archivo_static_si_no_referenciado(cursor, imagen_articulo)

        registrar_auditoria(
            conexion,
            "Artículo eliminado permanentemente",
            "articulo",
            articulo_id,
            {
                "codigo_articulo": articulo["codigo_articulo"],
                "nombre": articulo["nombre"],
                "imagen": imagen_articulo,
                "archivo_borrado": archivo_borrado,
            },
        )
        conexion.commit()
        return jsonify({"ok": True, "archivo_borrado": archivo_borrado})

    except Exception as error:
        conexion.rollback()
        print("Error al eliminar artículo permanentemente:", error)
        return jsonify({"ok": False, "error": "No se pudo eliminar permanentemente el artículo."}), 500
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
