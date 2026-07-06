# Facturas privadas VINOVA

Las facturas PDF ya no deben guardarse en `static/docs/facturas/` porque todo lo que vive dentro de `static/` puede quedar expuesto por URL directa.

A partir de esta versión:

- Las facturas nuevas se generan en `private/facturas/`.
- El navegador solo puede abrirlas mediante `/facturas/<id>/ver`.
- Esa ruta valida que el usuario sea el dueño de la factura o que tenga rol `ADMIN`/`TRABAJADOR`.
- Las facturas antiguas se migran con `migrations/migrar_facturas_privadas.py`.

## Aplicar migración

Desde la raíz del proyecto:

```powershell
.\venv\Scripts\python.exe .\migrations\aplicar_migraciones.py
```

También se puede correr solo esta migración:

```powershell
.\venv\Scripts\python.exe .\migrations\migrar_facturas_privadas.py .\vinova.db
```

La migración crea respaldo automático antes de tocar la base, copia los PDFs antiguos a `private/facturas/`, actualiza `facturas_vehiculo.archivo` y `facturas_vehiculo.archivo_pdf`, y elimina el PDF viejo de `static/docs/facturas/` cuando la copia privada fue exitosa.

## Configuración opcional

Puedes cambiar la ubicación privada con:

```env
PRIVATE_STORAGE_ROOT=C:\ruta\segura\vinova_private
```

En producción conviene que esa carpeta esté fuera del directorio público del servidor web.
