from vinova.core import *

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/contacto", methods=["POST"])
def contacto():

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    telefono = request.form.get("telefono", "").strip()
    asunto = request.form.get("asunto", "").strip() or "Solicitud desde formulario de contacto"
    mensaje = request.form.get("mensaje", "").strip()

    destino = request.referrer or url_for("inicio") + "#contacto"

    if not nombre or not correo or not mensaje:
        flash("Completa nombre, correo y mensaje para enviar la solicitud.", "warning")
        return redirect(destino)

    if "@" not in correo:
        flash("Ingresa un correo válido para que podamos responderte.", "warning")
        return redirect(destino)

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            INSERT INTO mensajes_contacto (
                nombre, correo, telefono, asunto, mensaje, ip, user_agent, estado, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Nuevo', ?)
        """, (
            nombre,
            correo,
            telefono,
            asunto,
            mensaje,
            obtener_ip_cliente(),
            request.headers.get("User-Agent", ""),
            fecha_actual()
        ))
        conexion.commit()

        mensaje_html = html.escape(mensaje).replace(chr(10), '<br>')
        texto_admin = (
            "Nueva solicitud de contacto en VINOVA\n\n"
            f"Nombre: {nombre}\n"
            f"Correo: {correo}\n"
            f"Teléfono: {telefono or 'N/D'}\n"
            f"Asunto: {asunto}\n\n"
            f"Mensaje:\n{mensaje}"
        )
        html_admin = plantilla_correo(
            "Nueva solicitud de contacto",
            f"""
            <p><strong>Nombre:</strong> {html.escape(nombre)}</p>
            <p><strong>Correo:</strong> {html.escape(correo)}</p>
            <p><strong>Teléfono:</strong> {html.escape(telefono or 'N/D')}</p>
            <p><strong>Asunto:</strong> {html.escape(asunto)}</p>
            <p><strong>Mensaje:</strong></p>
            <p>{mensaje_html}</p>
            """
        )
        enviar_correo(CONTACT_EMAIL, f"VINOVA | Contacto: {asunto}", texto_admin, html_admin, reply_to=correo)

        texto_cliente = (
            f"Hola {nombre},\n\n"
            "Recibimos tu solicitud de contacto en VINOVA. Nuestro equipo revisará el mensaje y responderá lo antes posible.\n\n"
            f"Asunto: {asunto}\n"
        )
        html_cliente = plantilla_correo(
            "Solicitud recibida",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>Recibimos tu solicitud de contacto en VINOVA. Nuestro equipo revisará el mensaje y responderá lo antes posible.</p>
            <p><strong>Asunto:</strong> {html.escape(asunto)}</p>
            """
        )
        enviar_correo(correo, "VINOVA | Hemos recibido tu mensaje", texto_cliente, html_cliente)

        flash("Mensaje registrado correctamente. La estructura de correo quedó preparada para envío real cuando se configure SMTP.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al guardar/enviar contacto:", error)
        flash("No se pudo enviar el mensaje de contacto. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect(url_for("inicio") + "#contacto")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        if "usuario_id" in session:
            return redirect("/perfil")

        return render_template("login.html")

    correo = request.form["email"].strip().lower()
    password = request.form["password"]

    segundos_restantes = segundos_bloqueo_login(correo)

    if segundos_restantes > 0:
        minutos = max(1, segundos_restantes // 60)
        flash(f"Demasiados intentos fallidos. Intenta nuevamente en {minutos} minuto(s).", "warning")
        return redirect("/login")

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,)
    )

    usuario = cursor.fetchone()
    conexion.close()

    if not usuario:
        registrar_login_fallido(correo)
        flash("Correo o contraseña incorrectos.", "error")
        return redirect("/login")

    if not check_password_hash(usuario["password"], password):
        registrar_login_fallido(correo)
        flash("Correo o contraseña incorrectos.", "error")
        return redirect("/login")

    if usuario.keys() and "activo" in usuario.keys() and usuario["activo"] == 0:
        registrar_login_fallido(correo)
        flash("Esta cuenta está desactivada. Contacta con administración.", "warning")
        return redirect("/login")

    limpiar_login_fallido(correo)

    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["usuario"] = usuario["nombre"]
    session["rol"] = usuario["rol"]
    session["foto_perfil"] = usuario["foto_perfil"]

    conexion_auditoria = conectar_db()
    try:
        registrar_auditoria(
            conexion_auditoria,
            "Inicio de sesión",
            "usuario",
            usuario["id"],
            {"correo": usuario["correo"], "rol": usuario["rol"]}
        )
        conexion_auditoria.commit()
    except Exception as error:
        conexion_auditoria.rollback()
        print("Advertencia: no se pudo auditar inicio de sesión:", error)
    finally:
        conexion_auditoria.close()

    return redirect("/perfil")


@app.route("/recuperar", methods=["POST"])
def recuperar_password():

    correo = (
        request.form.get("correo", "")
        or request.form.get("email", "")
    ).strip().lower()

    if not correo or "@" not in correo:
        flash("Ingresa un correo válido para solicitar recuperación de contraseña.", "warning")
        return redirect(url_for("login"))

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT id, nombre, correo, activo
            FROM usuarios
            WHERE correo = ?
            LIMIT 1
        """, (correo,))
        usuario = cursor.fetchone()

        if usuario and usuario["activo"] == 1:
            token = secrets.token_urlsafe(40)
            token_hash = generar_hash_token(token)
            expira = (datetime.now() + timedelta(minutes=PASSWORD_RESET_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                UPDATE usuarios
                SET reset_token_hash = ?,
                    reset_token_expira = ?,
                    actualizado_en = ?
                WHERE id = ?
            """, (
                token_hash,
                expira,
                fecha_actual(),
                usuario["id"]
            ))
            conexion.commit()

            enlace = construir_url_absoluta("restablecer_password", token=token)
            texto = (
                f"Hola {usuario['nombre']},\n\n"
                f"Solicitamos el restablecimiento de contraseña de tu cuenta VINOVA. "
                f"Abre este enlace antes de {PASSWORD_RESET_MINUTES} minutos:\n{enlace}\n\n"
                "Si no solicitaste este cambio, ignora este mensaje."
            )
            contenido_html = plantilla_correo(
                "Recuperación de contraseña",
                f"""
                <p>Hola <strong>{html.escape(usuario['nombre'])}</strong>,</p>
                <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta VINOVA.</p>
                <p>El enlace estará disponible durante <strong>{PASSWORD_RESET_MINUTES} minutos</strong>.</p>
                <p>Si no solicitaste este cambio, puedes ignorar este mensaje.</p>
                """,
                "Restablecer contraseña",
                enlace
            )
            enviar_correo(usuario["correo"], "VINOVA | Recuperación de contraseña", texto, contenido_html)
        else:
            conexion.rollback()

    except Exception as error:
        conexion.rollback()
        print("Error al procesar recuperación de contraseña:", error)

    finally:
        conexion.close()

    flash("Si el correo pertenece a una cuenta activa, se generó la solicitud de recuperación. En modo simulado, revisa la consola para ver el enlace.", "info")
    return redirect(url_for("login"))


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer_password(token):

    token = str(token or "").strip()

    if not token:
        flash("Enlace de recuperación inválido.", "warning")
        return redirect(url_for("login"))

    token_hash = generar_hash_token(token)
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id, nombre, correo, reset_token_expira, activo
        FROM usuarios
        WHERE reset_token_hash = ?
        LIMIT 1
    """, (token_hash,))
    usuario = cursor.fetchone()

    if not usuario or usuario["activo"] != 1:
        conexion.close()
        flash("El enlace de recuperación no es válido o ya fue utilizado.", "warning")
        return redirect(url_for("login"))

    try:
        expira = datetime.strptime(str(usuario["reset_token_expira"]), "%Y-%m-%d %H:%M:%S")
    except Exception:
        expira = datetime.min

    if expira < datetime.now():
        cursor.execute("""
            UPDATE usuarios
            SET reset_token_hash = NULL,
                reset_token_expira = NULL
            WHERE id = ?
        """, (usuario["id"],))
        conexion.commit()
        conexion.close()
        flash("El enlace de recuperación expiró. Solicita uno nuevo.", "warning")
        return redirect(url_for("login"))

    if request.method == "GET":
        conexion.close()
        return render_template("reset_password.html", token=token, usuario=usuario)

    nueva_password = request.form.get("password", "")
    confirmar_password = request.form.get("confirmar_password", "")

    if len(nueva_password) < 8:
        conexion.close()
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("restablecer_password", token=token))

    if nueva_password != confirmar_password:
        conexion.close()
        flash("Las contraseñas no coinciden.", "warning")
        return redirect(url_for("restablecer_password", token=token))

    try:
        cursor.execute("""
            UPDATE usuarios
            SET password = ?,
                reset_token_hash = NULL,
                reset_token_expira = NULL,
                actualizado_en = ?
            WHERE id = ?
        """, (
            generate_password_hash(nueva_password),
            fecha_actual(),
            usuario["id"]
        ))
        registrar_auditoria(
            conexion,
            "Contraseña restablecida",
            "usuario",
            usuario["id"],
            {"correo": usuario["correo"]}
        )
        conexion.commit()

        contenido_html = plantilla_correo(
            "Contraseña actualizada",
            f"""
            <p>Hola <strong>{html.escape(usuario['nombre'])}</strong>,</p>
            <p>La contraseña de tu cuenta VINOVA fue actualizada correctamente.</p>
            <p>Si no realizaste este cambio, comunícate con administración inmediatamente.</p>
            """
        )
        enviar_correo(usuario["correo"], "VINOVA | Contraseña actualizada", "Tu contraseña de VINOVA fue actualizada correctamente.", contenido_html)

        flash("Contraseña actualizada correctamente. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))

    except Exception as error:
        conexion.rollback()
        print("Error al restablecer contraseña:", error)
        flash("No se pudo actualizar la contraseña. Intenta nuevamente.", "error")
        return redirect(url_for("restablecer_password", token=token))

    finally:
        conexion.close()


@app.route("/register", methods=["POST"])
def register():

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")

    if not nombre or not correo or not password:
        flash("Nombre, correo y contraseña son obligatorios.", "warning")
        return redirect(url_for("login"))

    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("login"))

    conexion = conectar_db()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            "SELECT id FROM usuarios WHERE correo = ?",
            (correo,)
        )

        if cursor.fetchone():
            flash("Este correo ya está registrado.", "warning")
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)
        ahora = fecha_actual()

        cursor.execute("""
            INSERT INTO usuarios (
                nombre,
                correo,
                password,
                rol,
                activo,
                creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            nombre,
            correo,
            password_hash,
            "USUARIO",
            1,
            ahora
        ))
        nuevo_usuario_id = cursor.lastrowid

        registrar_auditoria(
            conexion,
            "Cuenta pública registrada",
            "usuario",
            nuevo_usuario_id,
            {"nombre": nombre, "correo": correo}
        )
        conexion.commit()

        usuario_correo = {
            "nombre": nombre,
            "correo": correo,
            "notificar_correo": 1,
            "notificar_mantenimientos": 1,
            "notificar_alertas": 1,
            "notificar_facturas": 1
        }
        contenido_html = plantilla_correo(
            "Cuenta creada correctamente",
            f"""
            <p>Hola <strong>{html.escape(nombre)}</strong>,</p>
            <p>Tu cuenta en VINOVA fue creada correctamente. Ya puedes iniciar sesión y registrar vehículos mediante códigos de activación.</p>
            """,
            "Iniciar sesión",
            construir_url_absoluta("login")
        )
        enviar_correo_usuario(
            usuario_correo,
            "general",
            "VINOVA | Cuenta creada",
            "Tu cuenta en VINOVA fue creada correctamente.",
            contenido_html
        )

        flash("Cuenta creada correctamente.", "success")

    except Exception as error:
        conexion.rollback()
        print("Error al registrar usuario público:", error)
        flash("No se pudo crear la cuenta. Intenta nuevamente.", "error")

    finally:
        conexion.close()

    return redirect(url_for("login"))
