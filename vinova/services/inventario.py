from __future__ import annotations

import sqlite3
from typing import Optional


def obtener_concesionario_facturacion(
    cursor,
    usuario_id: Optional[int],
    establecimiento_id: Optional[int] = None,
    establecimiento_nombre: str = "",
) -> dict:
    """Resuelve la concesionaria desde la que se factura y descuenta stock."""

    if establecimiento_id:
        cursor.execute("""
            SELECT id, nombre
            FROM establecimientos
            WHERE id = ?
              AND COALESCE(activo, 1) = 1
              AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
        """, (establecimiento_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row["id"], "nombre": row["nombre"]}

    establecimiento_nombre = str(establecimiento_nombre or "").strip()
    if establecimiento_nombre:
        cursor.execute("""
            SELECT id, nombre
            FROM establecimientos
            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))
              AND COALESCE(activo, 1) = 1
              AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
            LIMIT 1
        """, (establecimiento_nombre,))
        row = cursor.fetchone()
        if row:
            return {"id": row["id"], "nombre": row["nombre"]}

    usuario = None
    try:
        cursor.execute("""
            SELECT establecimiento_id, establecimiento
            FROM usuarios
            WHERE id = ?
        """, (usuario_id,))
        usuario = cursor.fetchone()
    except sqlite3.OperationalError:
        cursor.execute("SELECT establecimiento FROM usuarios WHERE id = ?", (usuario_id,))
        usuario = cursor.fetchone()

    if usuario:
        try:
            usuario_establecimiento_id = usuario["establecimiento_id"]
        except Exception:
            usuario_establecimiento_id = None

        if usuario_establecimiento_id:
            cursor.execute("""
                SELECT id, nombre
                FROM establecimientos
                WHERE id = ?
                  AND COALESCE(activo, 1) = 1
                  AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
            """, (usuario_establecimiento_id,))
            row = cursor.fetchone()
            if row:
                return {"id": row["id"], "nombre": row["nombre"]}

        try:
            nombre_usuario = str(usuario["establecimiento"] or "").strip()
        except Exception:
            nombre_usuario = ""

        if nombre_usuario:
            cursor.execute("""
                SELECT id, nombre
                FROM establecimientos
                WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))
                  AND COALESCE(activo, 1) = 1
                  AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
                LIMIT 1
            """, (nombre_usuario,))
            row = cursor.fetchone()
            if row:
                return {"id": row["id"], "nombre": row["nombre"]}

    cursor.execute("""
        SELECT id, nombre
        FROM establecimientos
        WHERE COALESCE(activo, 1) = 1
          AND LOWER(TRIM(COALESCE(tipo, ''))) = 'concesionario'
        ORDER BY COALESCE(distancia_km, 999999), nombre
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        return {"id": row["id"], "nombre": row["nombre"]}

    return {"id": None, "nombre": "VINOVA"}


def recalcular_stock_articulo_concesionarias(cursor, articulo_id: int, usuario_id: Optional[int] = None) -> None:
    """Sincroniza stock total del artículo desde su stock por concesionaria."""

    from vinova.core import fecha_actual, normalizar_precio

    try:
        cursor.execute("""
            SELECT COALESCE(SUM(stock), 0) AS stock_total,
                   COALESCE(SUM(unidades_vendidas), 0) AS vendidas_total
            FROM articulo_stock_establecimiento
            WHERE articulo_id = ?
        """, (articulo_id,))
        row = cursor.fetchone()
        stock_total = normalizar_precio(row["stock_total"] if row else 0) or 0
        vendidas_total = normalizar_precio(row["vendidas_total"] if row else 0) or 0
        cursor.execute("""
            UPDATE articulos
            SET stock = ?,
                unidades_vendidas = ?,
                estado = CASE WHEN ? <= 0 THEN 'Agotado' ELSE 'Disponible' END,
                actualizado_por = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (stock_total, vendidas_total, stock_total, usuario_id, fecha_actual(), articulo_id))
    except sqlite3.OperationalError:
        return
