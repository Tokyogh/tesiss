# Inventario por concesionaria

El inventario de artículos se divide por concesionarias activas.

Un establecimiento cuenta para disponibilidad pública solo cuando:

- `establecimientos.activo = 1`
- `establecimientos.tipo = 'concesionario'`
- el artículo tiene `stock > 0` en `articulo_stock_establecimiento`

## Mensajes públicos

| Caso | Mensaje |
|---|---|
| Stock en 0 concesionarias | Agotado temporalmente |
| Stock en 1 concesionaria | Disponible en 1 sucursal |
| Stock en 2 o más concesionarias | Disponible en tu VINOVA más cercano |

## Gestión en admin

En el panel de artículos, administración puede:

- registrar stock por cada concesionaria;
- editar stock por cada concesionaria;
- transferir stock entre concesionarias;
- revisar el último movimiento de cada artículo.

Cada ajuste registra un movimiento en `articulo_movimientos` con:

- artículo;
- concesionaria afectada;
- tipo de movimiento;
- cantidad;
- stock anterior;
- stock nuevo;
- usuario;
- fecha.

## Facturación

Las facturas con artículos descuentan stock únicamente desde una concesionaria activa.

Si el usuario operativo no tiene una concesionaria válida asignada, el sistema usa la concesionaria activa más cercana según `distancia_km`.

## Migraciones

Ejecuta todas las migraciones pendientes:

```bash
python migrations/aplicar_migraciones.py
```

O solo la migración de stock por concesionaria:

```bash
python migrations/migrar_stock_concesionarias_articulos.py
```
