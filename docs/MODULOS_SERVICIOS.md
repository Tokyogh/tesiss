# Separación por módulos

El proyecto mantiene las rutas Flask en `vinova/routes/`, pero la lógica pesada empezó a moverse a `vinova/services/`.

## Módulos agregados

- `vinova/services/storage.py`: normalización de rutas privadas, compatibilidad con facturas antiguas y borrado seguro de PDFs privados.
- `vinova/services/facturas.py`: generación de PDF, registro de factura y entrega protegida del archivo.
- `vinova/services/inventario.py`: resolución de concesionaria para facturación y recálculo de stock por concesionaria.

## Regla recomendada

Las rutas deberían encargarse de leer formularios, validar permisos y redirigir. La lógica de negocio debe vivir en `services/`.

Eso evita que `admin.py`, `trabajador.py`, `perfil.py` y `core.py` sigan creciendo sin control.
