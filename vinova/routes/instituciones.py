from vinova.core import *


@app.route("/instituciones")
def instituciones():
    tipo = request.args.get("tipo", "").strip()
    tipos_validos = {"institucion", "concesionario", "centro_atencion"}
    if tipo not in tipos_validos:
        tipo = ""

    conexion = conectar_db()
    cursor = conexion.cursor()

    establecimientos = listar_establecimientos(cursor, incluir_inactivos=False)
    conteos = contar_establecimientos_por_tipo(establecimientos)

    if tipo:
        establecimientos_filtrados = [item for item in establecimientos if item.get("tipo") == tipo]
    else:
        establecimientos_filtrados = establecimientos

    conexion.close()

    return render_template(
        "instituciones.html",
        establecimientos=establecimientos_filtrados,
        establecimientos_todos=establecimientos,
        conteos_establecimientos=conteos,
        tipo_activo=tipo,
        tipos_establecimiento=TIPOS_ESTABLECIMIENTO,
        maptiler_key=os.getenv("MAPTILER_KEY", ""),
    )
