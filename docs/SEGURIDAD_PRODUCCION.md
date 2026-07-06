# Seguridad para producción

Antes de publicar VINOVA:

## Entorno

- Usa una `FLASK_SECRET_KEY` larga, aleatoria y privada.
- Activa `FLASK_DEBUG=0`.
- Si sirves por HTTPS, activa `FLASK_COOKIE_SECURE=1`.
- No subas `.env`, bases `.db`, backups ni `venv`.
- Configura `APP_BASE_URL` con el dominio real.

## Base de datos

- Ejecuta migraciones con:

```bash
python migrations/aplicar_migraciones.py
```

- Haz respaldo antes de importar datos reales.
- Revisa que cada trabajador tenga `establecimiento_id` de una concesionaria activa.

## Archivos

- Mantén `MAX_UPLOAD_MB` en un valor razonable.
- Acepta solo extensiones necesarias.
- No guardes documentos sensibles dentro de carpetas públicas si no deben ser visibles por URL.

## Frontend

- Evita insertar datos de usuario con `innerHTML`.
- Si necesitas renderizar HTML dinámico, escapa valores antes de insertarlos.
- Revisa especialmente archivos en `static/js/` cuando agregues nuevas APIs.

## Operación

- Usa usuarios separados para admin y trabajadores.
- No compartas la misma cuenta de administrador.
- Revisa `auditoria_acciones` y `articulo_movimientos` cuando haya descuadres de stock.
