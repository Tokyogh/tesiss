
import os
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "vinova.db")


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    if not os.path.exists(DB_PATH):
        print(f"No encontré la base de datos: {DB_PATH}")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS establecimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL CHECK (tipo IN ('institucion', 'concesionario', 'centro_atencion')),
            descripcion TEXT DEFAULT '',
            direccion TEXT NOT NULL DEFAULT '',
            ciudad TEXT DEFAULT '',
            provincia TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
            correo TEXT DEFAULT '',
            horario TEXT DEFAULT '',
            website TEXT DEFAULT '',
            imagen TEXT DEFAULT '',
            servicios TEXT DEFAULT '[]',
            distancia_km REAL DEFAULT 0,
            lat REAL,
            lng REAL,
            pin_x REAL DEFAULT 50,
            pin_y REAL DEFAULT 50,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_por INTEGER,
            actualizado_por INTEGER,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY (actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_establecimientos_tipo ON establecimientos(tipo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_establecimientos_activo ON establecimientos(activo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_establecimientos_nombre ON establecimientos(nombre)")

    fecha = ahora()
    semillas = [
        (
            "Concesionario VINOVA Centro",
            "concesionario",
            "Concesionario oficial VINOVA para venta, financiamiento y prueba de manejo.",
            "Av. Reforma 1234, Centro",
            "Guayaquil",
            "Guayas",
            "+593 2 395 8721",
            "centro@vinova.ec",
            "Lun - Vie: 08:00 - 19:00 · Sáb: 08:00 - 15:00",
            "",
            "",
            '["Venta de vehículos", "Financiamiento", "Prueba de manejo", "Servicio postventa"]',
            2.4,
            -2.170998,
            -79.922359,
            28,
            38,
            1,
            fecha,
            fecha,
        ),
        (
            "Institución Afiliada VINOVA Norte",
            "institucion",
            "Alianza estratégica para programas, capacitación y beneficios institucionales.",
            "Av. Principal Norte 450",
            "Guayaquil",
            "Guayas",
            "+593 4 210 4455",
            "alianzas@vinova.ec",
            "Lun - Vie: 09:00 - 17:00",
            "",
            "",
            '["Convenios", "Capacitación", "Beneficios", "Información institucional"]',
            6.8,
            -2.145000,
            -79.910000,
            56,
            50,
            1,
            fecha,
            fecha,
        ),
        (
            "Centro de Atención VINOVA Sur",
            "centro_atencion",
            "Edificio enfocado en atención al cliente, consultas, soporte y gestión postventa.",
            "Periférico Sur 5678",
            "Guayaquil",
            "Guayas",
            "+593 4 265 7857",
            "atencion.sur@vinova.ec",
            "Lun - Vie: 08:30 - 18:30 · Sáb: 09:00 - 14:00",
            "",
            "",
            '["Atención al cliente", "Soporte", "Garantías", "Información de servicios"]',
            12.5,
            -2.219000,
            -79.920000,
            42,
            70,
            1,
            fecha,
            fecha,
        ),
    ]

    cur.executemany("""
        INSERT OR IGNORE INTO establecimientos (
            nombre, tipo, descripcion, direccion, ciudad, provincia, telefono, correo,
            horario, website, imagen, servicios, distancia_km, lat, lng, pin_x, pin_y,
            activo, creado_en, actualizado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, semillas)

    con.commit()
    con.close()
    print("Migración de establecimientos aplicada correctamente.")


if __name__ == "__main__":
    main()
