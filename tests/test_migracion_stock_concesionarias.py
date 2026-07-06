from __future__ import annotations

import sqlite3
import unittest

from migrations.migrar_stock_concesionarias_articulos import (
    concesionarias_activas,
    crear_tablas_base,
    migrar_stock_global_a_concesionaria,
    recalcular_totales_articulos,
)


class MigracionStockConcesionariasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.cur.execute("""
            CREATE TABLE establecimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                distancia_km REAL DEFAULT 0
            )
        """)
        crear_tablas_base(self.cur)

    def tearDown(self) -> None:
        self.con.close()

    def test_migra_stock_global_a_primera_concesionaria(self) -> None:
        self.cur.execute("""
            INSERT INTO establecimientos (nombre, tipo, activo, distancia_km)
            VALUES ('Centro', 'concesionario', 1, 1), ('Norte', 'concesionario', 1, 5)
        """)
        self.cur.execute("""
            INSERT INTO articulos (
                codigo_articulo, nombre, categoria, precio, stock,
                stock_minimo, unidades_vendidas, creado_en, actualizado_en
            )
            VALUES ('ART-1', 'Aceite', 'Aceites', 10, 12, 2, 3, '2026-01-01', '2026-01-01')
        """)

        sedes = concesionarias_activas(self.cur)
        migrados = migrar_stock_global_a_concesionaria(self.cur, sedes[0]["id"])

        self.assertEqual(migrados, 1)
        row = self.cur.execute("""
            SELECT stock, stock_minimo, unidades_vendidas
            FROM articulo_stock_establecimiento
            WHERE articulo_id = 1 AND establecimiento_id = ?
        """, (sedes[0]["id"],)).fetchone()
        self.assertEqual(row["stock"], 12)
        self.assertEqual(row["stock_minimo"], 2)
        self.assertEqual(row["unidades_vendidas"], 3)

    def test_no_duplica_si_ya_existe_stock_en_concesionaria(self) -> None:
        self.cur.execute("""
            INSERT INTO establecimientos (nombre, tipo, activo, distancia_km)
            VALUES ('Centro', 'concesionario', 1, 1)
        """)
        self.cur.execute("""
            INSERT INTO articulos (
                codigo_articulo, nombre, categoria, precio, stock,
                stock_minimo, creado_en, actualizado_en
            )
            VALUES ('ART-2', 'Filtro', 'Filtros', 8, 7, 1, '2026-01-01', '2026-01-01')
        """)
        self.cur.execute("""
            INSERT INTO articulo_stock_establecimiento (
                articulo_id, establecimiento_id, stock, stock_minimo,
                unidades_vendidas, creado_en, actualizado_en
            )
            VALUES (1, 1, 4, 1, 0, '2026-01-01', '2026-01-01')
        """)

        migrados = migrar_stock_global_a_concesionaria(self.cur, 1)
        count = self.cur.execute("SELECT COUNT(*) AS total FROM articulo_stock_establecimiento").fetchone()

        self.assertEqual(migrados, 0)
        self.assertEqual(count["total"], 1)

    def test_recalcula_total_desde_concesionarias(self) -> None:
        self.cur.execute("""
            INSERT INTO establecimientos (nombre, tipo, activo, distancia_km)
            VALUES ('Centro', 'concesionario', 1, 1), ('Sur', 'concesionario', 1, 2)
        """)
        self.cur.execute("""
            INSERT INTO articulos (
                codigo_articulo, nombre, categoria, precio, stock,
                stock_minimo, creado_en, actualizado_en
            )
            VALUES ('ART-3', 'Bateria', 'Baterías', 80, 0, 0, '2026-01-01', '2026-01-01')
        """)
        self.cur.executemany("""
            INSERT INTO articulo_stock_establecimiento (
                articulo_id, establecimiento_id, stock, stock_minimo,
                unidades_vendidas, creado_en, actualizado_en
            )
            VALUES (1, ?, ?, ?, 0, '2026-01-01', '2026-01-01')
        """, [(1, 3, 1), (2, 5, 2)])

        recalcular_totales_articulos(self.cur)
        row = self.cur.execute("SELECT stock, stock_minimo FROM articulos WHERE id = 1").fetchone()

        self.assertEqual(row["stock"], 8)
        self.assertEqual(row["stock_minimo"], 2)


if __name__ == "__main__":
    unittest.main()
