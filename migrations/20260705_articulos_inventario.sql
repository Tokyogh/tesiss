-- VINOVA - Módulo de artículos e inventario
-- Ejecutar una sola vez sobre vinova.db.

CREATE TABLE IF NOT EXISTS articulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_articulo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'Otros',
    marca TEXT DEFAULT '',
    proveedor TEXT DEFAULT '',
    descripcion TEXT DEFAULT '',
    imagen TEXT DEFAULT '',
    precio REAL NOT NULL DEFAULT 0,
    costo REAL DEFAULT 0,
    stock REAL NOT NULL DEFAULT 0,
    stock_minimo REAL DEFAULT 0,
    unidad TEXT DEFAULT 'Unidad',
    estado TEXT DEFAULT 'Disponible',
    activo INTEGER NOT NULL DEFAULT 1,
    unidades_vendidas REAL NOT NULL DEFAULT 0,
    archivado INTEGER NOT NULL DEFAULT 0,
    archivado_en TEXT,
    archivado_por INTEGER,
    motivo_archivado TEXT,
    creado_por INTEGER,
    actualizado_por INTEGER,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (archivado_por) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS articulo_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    articulo_id INTEGER NOT NULL,
    tipo_movimiento TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 0,
    stock_anterior REAL NOT NULL DEFAULT 0,
    stock_nuevo REAL NOT NULL DEFAULT 0,
    referencia_tipo TEXT DEFAULT '',
    referencia_id INTEGER,
    descripcion TEXT DEFAULT '',
    creado_por INTEGER,
    creado_en TEXT NOT NULL,
    FOREIGN KEY (articulo_id) REFERENCES articulos(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS factura_articulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id INTEGER NOT NULL,
    articulo_id INTEGER,
    codigo_articulo TEXT DEFAULT '',
    nombre_articulo TEXT NOT NULL,
    categoria TEXT DEFAULT '',
    cantidad REAL NOT NULL DEFAULT 1,
    unidad TEXT DEFAULT 'Unidad',
    precio_unitario REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL,
    FOREIGN KEY (factura_id) REFERENCES facturas_vehiculo(id) ON DELETE CASCADE,
    FOREIGN KEY (articulo_id) REFERENCES articulos(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_articulos_estado ON articulos(activo, archivado, categoria);
CREATE INDEX IF NOT EXISTS idx_articulos_nombre ON articulos(nombre, codigo_articulo, marca);
CREATE INDEX IF NOT EXISTS idx_articulo_movimientos_articulo ON articulo_movimientos(articulo_id, creado_en);
CREATE INDEX IF NOT EXISTS idx_factura_articulos_factura ON factura_articulos(factura_id);
