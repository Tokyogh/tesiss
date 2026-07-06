from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def find_db_path() -> Path:
    if len(sys.argv) > 2:
        print("Uso: python migrar_facturas_privadas.py [ruta/a/vinova.db]")
        sys.exit(1)

    if len(sys.argv) == 2:
        return Path(sys.argv[1]).resolve()

    candidates = [
        Path.cwd() / "vinova.db",
        SCRIPT_DIR / "vinova.db",
        SCRIPT_DIR.parent / "vinova.db",
    ]

    for start in {Path.cwd(), SCRIPT_DIR, SCRIPT_DIR.parent}:
        current = start.resolve()
        while True:
            candidates.append(current / "vinova.db")
            if current.parent == current:
                break
            current = current.parent

    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    return (Path.cwd() / "vinova.db").resolve()


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def tabla_existe(cur: sqlite3.Cursor, tabla: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cur.fetchone() is not None


def columna_existe(cur: sqlite3.Cursor, tabla: str, columna: str) -> bool:
    if not tabla_existe(cur, tabla):
        return False
    cur.execute(f"PRAGMA table_info({tabla})")
    return any(row[1] == columna for row in cur.fetchall())


def normalizar_texto_ruta(valor: str) -> str:
    texto = str(valor or "").strip().replace("\\", "/")
    if not texto:
        return ""
    if texto.lower().startswith(("http://", "https://")):
        return ""
    texto = texto.split("?", 1)[0].split("#", 1)[0].strip().lstrip("/")
    while "//" in texto:
        texto = texto.replace("//", "/")
    if ".." in texto.split("/"):
        return ""
    return texto


def nombre_factura_desde_ruta(valor: str) -> str:
    texto = normalizar_texto_ruta(valor)
    if not texto:
        return ""
    nombre = os.path.basename(texto)
    if not nombre.lower().endswith(".pdf"):
        return ""
    return nombre


def ruta_privada_desde_ruta(valor: str) -> str:
    nombre = nombre_factura_desde_ruta(valor)
    if not nombre:
        return ""
    return f"facturas/{nombre}"


def es_ruta_factura_migrable(valor: str) -> bool:
    texto = normalizar_texto_ruta(valor).lower()
    if not texto:
        return False
    return (
        texto.startswith("docs/facturas/")
        or texto.startswith("static/docs/facturas/")
        or texto.startswith("/static/docs/facturas/")
        or texto.startswith("facturas/")
        or texto.startswith("private/facturas/")
    ) and texto.endswith(".pdf")


def copiar_a_privado(base_dir: Path, ruta_guardada: str, eliminaciones_pendientes: set[Path]) -> str:
    nombre = nombre_factura_desde_ruta(ruta_guardada)
    if not nombre:
        return ""

    private_dir = base_dir / "private" / "facturas"
    static_dir = base_dir / "static" / "docs" / "facturas"
    private_dir.mkdir(parents=True, exist_ok=True)

    destino = private_dir / nombre
    origenes = [
        static_dir / nombre,
        base_dir / "static" / normalizar_texto_ruta(ruta_guardada).removeprefix("static/"),
        base_dir / normalizar_texto_ruta(ruta_guardada),
        destino,
    ]

    origen_valido = None
    for origen in origenes:
        try:
            origen = origen.resolve()
        except OSError:
            continue
        if origen.is_file():
            origen_valido = origen
            break

    if origen_valido and origen_valido != destino.resolve():
        if not destino.exists():
            shutil.copy2(origen_valido, destino)
        try:
            static_root = (base_dir / "static").resolve()
            if str(origen_valido).startswith(str(static_root) + os.sep):
                eliminaciones_pendientes.add(origen_valido)
        except OSError:
            pass

    if destino.exists():
        return f"facturas/{nombre}"
    return ""


def main() -> None:
    db_path = find_db_path()
    if not db_path.exists():
        print(f"No encontré la base de datos: {db_path}")
        sys.exit(1)

    base_dir = db_path.parent
    backup_path = base_dir / f"vinova_backup_facturas_privadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, backup_path)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    eliminaciones_pendientes: set[Path] = set()
    actualizadas = 0
    copiadas = 0

    try:
        cur = con.cursor()
        if not tabla_existe(cur, "facturas_vehiculo"):
            print("La tabla facturas_vehiculo no existe. No hay nada que migrar.")
            return

        columnas = [c for c in ("archivo", "archivo_pdf") if columna_existe(cur, "facturas_vehiculo", c)]
        if not columnas:
            print("No hay columnas de archivo en facturas_vehiculo. No hay nada que migrar.")
            return

        columnas_select = ["id", *columnas]
        cur.execute(f"SELECT {', '.join(columnas_select)} FROM facturas_vehiculo")
        facturas = cur.fetchall()

        for factura in facturas:
            ruta_original = ""
            if "archivo_pdf" in columnas:
                ruta_original = factura["archivo_pdf"] or ""
            if not ruta_original and "archivo" in columnas:
                ruta_original = factura["archivo"] or ""
            if not es_ruta_factura_migrable(ruta_original):
                continue

            ruta_privada = copiar_a_privado(base_dir, ruta_original, eliminaciones_pendientes)
            if not ruta_privada:
                continue

            updates = []
            params = []
            for columna in columnas:
                valor = factura[columna]
                if es_ruta_factura_migrable(valor):
                    updates.append(f"{columna} = ?")
                    params.append(ruta_privada)

            if updates:
                if columna_existe(cur, "facturas_vehiculo", "actualizado_en"):
                    updates.append("actualizado_en = ?")
                    params.append(ahora())
                params.append(factura["id"])
                cur.execute(f"UPDATE facturas_vehiculo SET {', '.join(updates)} WHERE id = ?", params)
                actualizadas += 1
                copiadas += 1

        con.commit()

        borradas = 0
        for path in sorted(eliminaciones_pendientes):
            try:
                path.unlink()
                borradas += 1
            except OSError:
                pass

        print(f"Backup creado: {backup_path}")
        print(f"Facturas actualizadas: {actualizadas}")
        print(f"Archivos movidos a private/facturas: {copiadas}")
        print(f"Archivos antiguos eliminados de static/docs/facturas: {borradas}")

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
