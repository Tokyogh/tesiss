from __future__ import annotations

import os
import shutil
from typing import Iterable


FACTURAS_PRIVADAS_SUBDIR = "facturas"


def private_storage_root() -> str:
    from vinova.core import app, BASE_DIR

    root = app.config.get("PRIVATE_STORAGE_ROOT")
    if not root:
        root_env = os.getenv("PRIVATE_STORAGE_ROOT", "").strip()
        if root_env:
            root = root_env if os.path.isabs(root_env) else os.path.join(BASE_DIR, root_env)
        else:
            root = os.path.join(BASE_DIR, "private")
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    return root


def private_invoice_folder() -> str:
    from vinova.core import app

    folder = app.config.get("INVOICE_FOLDER") or os.path.join(
        private_storage_root(),
        FACTURAS_PRIVADAS_SUBDIR,
    )
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    return folder


def legacy_static_invoice_folder() -> str:
    from vinova.core import app

    return os.path.abspath(
        app.config.get("LEGACY_INVOICE_STATIC_FOLDER")
        or os.path.join(app.static_folder, "docs", "facturas")
    )


def _limpiar_path_relativo(valor: str) -> str:
    texto = str(valor or "").strip().replace("\\", "/")
    if not texto:
        return ""
    if texto.lower().startswith(("http://", "https://")):
        return ""
    texto = texto.split("?", 1)[0].split("#", 1)[0].strip()
    texto = texto.lstrip("/")
    while "//" in texto:
        texto = texto.replace("//", "/")
    if ".." in texto.split("/"):
        return ""
    return texto


def normalizar_ruta_factura_privada(ruta: str) -> str:
    """Devuelve la ruta relativa dentro de private para una factura PDF.

    Formato nuevo preferido: ``facturas/<archivo>.pdf``.
    También entiende rutas antiguas de ``static/docs/facturas`` para poder
    resolverlas después de correr la migración.
    """

    texto = _limpiar_path_relativo(ruta)
    if not texto:
        return ""

    lower = texto.lower()
    prefijos_a_quitar = (
        "private/",
        "./private/",
        "static/",
        "./static/",
    )
    for prefijo in prefijos_a_quitar:
        if lower.startswith(prefijo):
            texto = texto[len(prefijo):]
            lower = texto.lower()
            break

    if lower.startswith("docs/facturas/"):
        texto = f"{FACTURAS_PRIVADAS_SUBDIR}/{os.path.basename(texto)}"
    elif lower.startswith("facturas/"):
        texto = f"{FACTURAS_PRIVADAS_SUBDIR}/{os.path.basename(texto)}"
    elif "/" not in texto:
        texto = f"{FACTURAS_PRIVADAS_SUBDIR}/{texto}"
    else:
        return ""

    nombre = os.path.basename(texto)
    if not nombre or not nombre.lower().endswith(".pdf"):
        return ""

    return f"{FACTURAS_PRIVADAS_SUBDIR}/{nombre}"


def ruta_absoluta_factura_privada(ruta: str) -> str:
    ruta_relativa = normalizar_ruta_factura_privada(ruta)
    if not ruta_relativa:
        return ""

    root = private_storage_root()
    absoluta = os.path.abspath(os.path.join(root, ruta_relativa))
    if not absoluta.startswith(root + os.sep):
        return ""
    return absoluta


def factura_privada_existe(ruta: str) -> bool:
    absoluta = ruta_absoluta_factura_privada(ruta)
    return bool(absoluta and os.path.isfile(absoluta))


def normalizar_ruta_factura_static_legacy(ruta: str) -> str:
    """Normaliza una factura antigua guardada dentro de static/docs/facturas."""

    from vinova.core import normalizar_ruta_static_documento

    texto = normalizar_ruta_static_documento(ruta)
    if not texto:
        return ""

    lower = texto.lower()
    if lower.startswith("docs/facturas/") and lower.endswith(".pdf"):
        return texto
    return ""


def rutas_candidatas_factura_legacy(ruta: str) -> Iterable[str]:
    texto = _limpiar_path_relativo(ruta)
    if not texto:
        return []

    nombre = os.path.basename(texto)
    if not nombre or not nombre.lower().endswith(".pdf"):
        return []

    return (
        f"docs/facturas/{nombre}",
        f"static/docs/facturas/{nombre}",
        texto,
    )


def preparar_destino_factura_privada(nombre_archivo: str) -> tuple[str, str]:
    nombre = os.path.basename(str(nombre_archivo or "").strip())
    if not nombre or not nombre.lower().endswith(".pdf"):
        raise ValueError("El nombre de factura privada debe ser un PDF.")

    ruta_relativa = f"{FACTURAS_PRIVADAS_SUBDIR}/{nombre}"
    ruta_absoluta = ruta_absoluta_factura_privada(ruta_relativa)
    os.makedirs(os.path.dirname(ruta_absoluta), exist_ok=True)
    return ruta_relativa, ruta_absoluta


def copiar_factura_static_a_privado(ruta_static_relativa: str, eliminar_origen: bool = False) -> str:
    """Copia una factura antigua de static/docs/facturas a private/facturas.

    Devuelve la nueva ruta relativa privada o cadena vacía si no pudo copiarse.
    """

    from vinova.core import app

    ruta_legacy = normalizar_ruta_factura_static_legacy(ruta_static_relativa)
    if not ruta_legacy:
        return ""

    origen = os.path.abspath(os.path.join(app.static_folder, ruta_legacy))
    static_root = os.path.abspath(app.static_folder)
    if not origen.startswith(static_root + os.sep) or not os.path.isfile(origen):
        return ""

    destino_relativo, destino_absoluto = preparar_destino_factura_privada(os.path.basename(origen))

    if not os.path.exists(destino_absoluto):
        shutil.copy2(origen, destino_absoluto)

    if eliminar_origen:
        try:
            os.remove(origen)
        except OSError:
            pass

    return destino_relativo


def _contar_referencia_factura_privada_columna(cursor, columna: str, ruta: str) -> int:
    from vinova.core import columna_existe_db, tabla_existe_db

    if not tabla_existe_db(cursor, "facturas_vehiculo") or not columna_existe_db(cursor, "facturas_vehiculo", columna):
        return 0

    nombre = os.path.basename(normalizar_ruta_factura_privada(ruta))
    if not nombre:
        return 0

    candidatos = (
        f"facturas/{nombre}",
        f"private/facturas/{nombre}",
        f"/private/facturas/{nombre}",
        f"docs/facturas/{nombre}",
        f"static/docs/facturas/{nombre}",
        f"/static/docs/facturas/{nombre}",
        nombre,
    )
    marcadores = ",".join("?" for _ in candidatos)
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM facturas_vehiculo
        WHERE REPLACE(TRIM(COALESCE({columna}, '')), '\\', '/') IN ({marcadores})
        """,
        candidatos,
    )
    return int(cursor.fetchone()[0] or 0)


def contar_referencias_factura_privada(cursor, ruta: str) -> int:
    ruta_normalizada = normalizar_ruta_factura_privada(ruta)
    if not ruta_normalizada:
        return 0
    return (
        _contar_referencia_factura_privada_columna(cursor, "archivo", ruta_normalizada)
        + _contar_referencia_factura_privada_columna(cursor, "archivo_pdf", ruta_normalizada)
    )


def eliminar_factura_privada_si_no_referenciada(cursor, ruta: str) -> bool:
    ruta_normalizada = normalizar_ruta_factura_privada(ruta)
    if not ruta_normalizada or contar_referencias_factura_privada(cursor, ruta_normalizada) > 0:
        return False

    absoluta = ruta_absoluta_factura_privada(ruta_normalizada)
    if not absoluta or os.path.basename(absoluta).lower() == ".gitkeep":
        return False

    if os.path.isfile(absoluta):
        try:
            os.remove(absoluta)
            return True
        except OSError:
            return False

    return False
