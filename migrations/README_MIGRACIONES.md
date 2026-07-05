# Migraciones VINOVA

Ejecutar siempre desde la raíz del proyecto:

```bash
python migrations/migrar_estructura_vinova.py
python migrations/migrar_auditoria_acciones.py
```

También puedes indicar la base manualmente:

```bash
python migrations/migrar_estructura_vinova.py vinova.db
python migrations/migrar_auditoria_acciones.py vinova.db
```

Ambas migraciones son idempotentes: se pueden ejecutar más de una vez.

## Establecimientos / Instituciones

Para crear la tabla usada por la página pública de instituciones y la asignación de establecimientos a trabajadores:

```bash
python migrations/migrar_establecimientos.py
```

También puedes indicar la ruta de la base:

```bash
python migrations/migrar_establecimientos.py vinova.db
```
