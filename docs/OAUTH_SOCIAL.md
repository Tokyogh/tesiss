# Login social con Google/Microsoft

Los botones de Google/Microsoft fueron retirados como acción directa porque no existía OAuth real configurado. Mostrar botones que no autentican realmente confunde al usuario y da una falsa sensación de seguridad.

Para habilitarlo correctamente en producción se necesita:

- crear una app OAuth en Google Cloud o Microsoft Entra;
- configurar URL de retorno autorizada;
- guardar `CLIENT_ID` y `CLIENT_SECRET` en `.env`;
- validar el `state` anti-CSRF del flujo OAuth;
- crear o vincular la cuenta local por correo verificado;
- definir qué rol se asigna a usuarios registrados por proveedor externo.

Mientras eso no esté configurado, VINOVA mantiene el login seguro por correo y contraseña.
