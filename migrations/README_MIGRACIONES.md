# Migraciones VINOVA

La forma recomendada de aplicar cambios pendientes es usar el runner versionado:

```bash
python migrations/aplicar_migraciones.py
```

O indicando la base manualmente:

```bash
python migrations/aplicar_migraciones.py vinova.db
```

El runner registra cada migración aplicada en `schema_migrations` para no repetirla accidentalmente.

## Migraciones incluidas

- `migrar_establecimientos.py`: establecimientos, instituciones y concesionarias.
- `20260705_articulos_inventario.sql`: tablas base de artículos e inventario.
- `migrar_stock_concesionarias_articulos.py`: stock de artículos por concesionaria.
- `migrar_auditoria_acciones.py`: auditoría de acciones sensibles.
- `migrar_notificaciones_usuario.py`: notificaciones internas.
- `migrar_facturas_privadas.py`: mueve facturas PDF de `static/docs/facturas` a `private/facturas`.

Todas las migraciones Python crean respaldo antes de modificar la base.
