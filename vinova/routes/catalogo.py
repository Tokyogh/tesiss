from vinova.core import *

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
            "LOWER(TRIM(COALESCE(combustible, ''))) IN (?, ?, ?, ?)",
            ("híbrido", "hibrido", "eléctrico", "electrico")
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


@app.route("/catalog/vehiculos/<int:vehiculo_id>/preview/guardar", methods=["POST"])
def catalog_guardar_preview_vehiculo(vehiculo_id):
    """Permite a ADMIN/TRABAJADOR editar desde el catálogo la ficha del preview 3D."""

    datos = request.get_json(silent=True) or {}
    descripcion = str(datos.get("descripcion", "") or "").strip()
    preview_sistemas_raw = datos.get("preview_sistemas_json", "")

    if not isinstance(preview_sistemas_raw, str):
        preview_sistemas_raw = json.dumps(preview_sistemas_raw, ensure_ascii=False)

    try:
        preview_sistemas_json = normalizar_preview_sistemas_json(preview_sistemas_raw)
    except ValueError as error:
        return jsonify({
            "ok": False,
            "message": str(error)
        }), 400

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, modelo_base_id
            FROM vehiculos
            WHERE id = ?
              AND COALESCE(archivado, 0) = 0
        """, (vehiculo_id,))
        vehiculo = cursor.fetchone()

        if not vehiculo:
            return jsonify({
                "ok": False,
                "message": "El vehículo no existe o fue archivado."
            }), 404

        ahora = fecha_actual()

        cursor.execute("""
            UPDATE vehiculos
            SET
                descripcion = ?,
                preview_sistemas_json = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (
            descripcion,
            preview_sistemas_json,
            ahora,
            vehiculo_id,
        ))

        modelo_base_id = vehiculo["modelo_base_id"] if "modelo_base_id" in vehiculo.keys() else None

        if modelo_base_id:
            cursor.execute("""
                UPDATE vehiculo_modelos
                SET
                    preview_sistemas_json = ?,
                    actualizado_en = ?
                WHERE id = ?
            """, (
                preview_sistemas_json,
                ahora,
                modelo_base_id,
            ))

        registrar_auditoria(
            conexion,
            "Preview de catálogo actualizado",
            "vehiculo",
            vehiculo_id,
            {"modelo_base_id": modelo_base_id}
        )
        conexion.commit()

        return jsonify({
            "ok": True,
            "message": "Información del preview actualizada.",
            "descripcion": descripcion,
            "preview_sistemas_json": preview_sistemas_json,
        })

    except Exception as error:
        conexion.rollback()
        print("Error al guardar preview 3D desde catálogo:", error)
        return jsonify({
            "ok": False,
            "message": "No se pudo guardar la información del preview."
        }), 500

    finally:
        conexion.close()
