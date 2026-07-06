# Notificaciones internas VINOVA

El sistema de notificaciones internas permite enviar mensajes desde el panel administrativo o trabajador hacia el perfil del usuario. No depende de correo externo.

## Uso operativo

- El usuario recibe la notificación en `Perfil > Notificaciones`.
- El admin entra a `Admin > Mensajes`.
- El trabajador entra a `Trabajador > Mensajes`.
- Ya no se usa un selector gigante de usuarios. El compositor tiene un buscador por nombre, correo, cédula, ID o rol.
- El trabajador solo puede buscar y escribir a cuentas con rol `USUARIO`.
- El admin puede buscar cuentas activas de cualquier rol.

## Tipos disponibles

- `mensaje`
- `alerta`
- `mantenimiento`
- `factura`

## Prioridades disponibles

- `normal`
- `alta`
- `urgente`

## Tabla principal

La tabla se crea con la migración:

```bash
python migrations/aplicar_migraciones.py
```

Tabla:

```txt
notificaciones_usuario
```

Campos clave:

- `usuario_id`: destinatario.
- `remitente_id`: admin/trabajador que envió el mensaje.
- `tipo`: categoría visual de la notificación.
- `prioridad`: prioridad mostrada al usuario.
- `titulo` y `mensaje`: contenido.
- `leida`: estado de lectura.
- `eliminado_usuario`: oculta la notificación en el perfil del usuario sin borrar el historial interno.

## Historial

Los paneles muestran mensajes recientes enviados:

- Admin: ve el historial reciente general.
- Trabajador: ve los mensajes enviados por su propia cuenta.

Esto evita que el formulario quede perdido dentro de la sección de usuarios y mejora el uso cuando existan cientos o miles de clientes.
