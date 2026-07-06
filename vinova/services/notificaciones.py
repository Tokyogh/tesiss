from __future__ import annotations

from vinova import core

# ================= NOTIFICACIONES INTERNAS =================

TIPOS_NOTIFICACION_USUARIO = {"mensaje", "alerta", "mantenimiento", "factura"}
PRIORIDADES_NOTIFICACION_USUARIO = {"normal", "alta", "urgente"}


def asegurar_tabla_notificaciones_usuario(cursor):
    """Crea la tabla de notificaciones internas si una base antigua aún no la tiene."""

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            remitente_id INTEGER,
            tipo TEXT DEFAULT 'mensaje',
            prioridad TEXT DEFAULT 'normal',
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            leida INTEGER DEFAULT 0,
            eliminado_usuario INTEGER DEFAULT 0,
            creado_en TEXT NOT NULL,
            leida_en TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (remitente_id) REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario_destino
        ON notificaciones_usuario(usuario_id, eliminado_usuario, leida, creado_en)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario_remitente
        ON notificaciones_usuario(remitente_id, creado_en)
    """)


def normalizar_tipo_notificacion(valor):
    tipo = str(valor or "mensaje").strip().lower()
    return tipo if tipo in TIPOS_NOTIFICACION_USUARIO else "mensaje"


def normalizar_prioridad_notificacion(valor):
    prioridad = str(valor or "normal").strip().lower()
    return prioridad if prioridad in PRIORIDADES_NOTIFICACION_USUARIO else "normal"


def crear_notificacion_usuario(
    conexion,
    usuario_id,
    titulo,
    mensaje,
    tipo="mensaje",
    prioridad="normal",
    remitente_id=None,
):
    """Registra un mensaje interno para el perfil del usuario."""

    if not conexion:
        return None

    titulo = str(titulo or "").strip()[:140]
    mensaje = str(mensaje or "").strip()[:1600]

    if not usuario_id or not titulo or not mensaje:
        return None

    cursor = conexion.cursor()
    asegurar_tabla_notificaciones_usuario(cursor)

    cursor.execute("""
        INSERT INTO notificaciones_usuario (
            usuario_id,
            remitente_id,
            tipo,
            prioridad,
            titulo,
            mensaje,
            leida,
            eliminado_usuario,
            creado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
    """, (
        usuario_id,
        remitente_id,
        normalizar_tipo_notificacion(tipo),
        normalizar_prioridad_notificacion(prioridad),
        titulo,
        mensaje,
        core.fecha_actual(),
    ))

    return cursor.lastrowid


def contar_notificaciones_usuario(cursor, usuario_id, solo_no_leidas=False):
    asegurar_tabla_notificaciones_usuario(cursor)

    condicion_leida = "AND COALESCE(leida, 0) = 0" if solo_no_leidas else ""
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM notificaciones_usuario
        WHERE usuario_id = ?
          AND COALESCE(eliminado_usuario, 0) = 0
          {condicion_leida}
    """, (usuario_id,))

    return cursor.fetchone()[0]


def listar_notificaciones_usuario(cursor, usuario_id, limite=80):
    asegurar_tabla_notificaciones_usuario(cursor)

    cursor.execute("""
        SELECT
            notificaciones_usuario.*,
            remitente.nombre AS remitente_nombre,
            remitente.rol AS remitente_rol,
            remitente.establecimiento AS remitente_establecimiento
        FROM notificaciones_usuario
        LEFT JOIN usuarios AS remitente
            ON remitente.id = notificaciones_usuario.remitente_id
        WHERE notificaciones_usuario.usuario_id = ?
          AND COALESCE(notificaciones_usuario.eliminado_usuario, 0) = 0
        ORDER BY COALESCE(notificaciones_usuario.leida, 0) ASC,
                 datetime(notificaciones_usuario.creado_en) DESC,
                 notificaciones_usuario.id DESC
        LIMIT ?
    """, (usuario_id, int(limite or 80)))

    notificaciones = []

    for fila in cursor.fetchall():
        item = dict(fila)
        item["creado_visible"] = core.formatear_fecha_visible(item.get("creado_en"))
        item["leida_visible"] = core.formatear_fecha_visible(item.get("leida_en"))
        item["tipo"] = normalizar_tipo_notificacion(item.get("tipo"))
        item["prioridad"] = normalizar_prioridad_notificacion(item.get("prioridad"))
        notificaciones.append(item)

    return notificaciones



def buscar_destinatarios_notificacion(cursor, termino, solo_clientes=False, limite=12):
    """Busca usuarios activos para el compositor de mensajes sin cargar listas gigantes."""

    termino = str(termino or "").strip()
    limite = max(1, min(int(limite or 12), 25))

    if len(termino) < 2:
        return []

    patron = f"%{termino.lower()}%"
    filtro_rol = "AND usuarios.rol = 'USUARIO'" if solo_clientes else ""
    id_buscado = int(termino) if termino.isdigit() else -1

    cursor.execute(f"""
        SELECT
            usuarios.id,
            usuarios.nombre,
            usuarios.correo,
            usuarios.cedula,
            usuarios.rol,
            usuarios.establecimiento,
            COALESCE(usuarios.activo, 1) AS activo,
            COUNT(usuarios_vehiculos.id) AS total_vehiculos
        FROM usuarios
        LEFT JOIN usuarios_vehiculos
            ON usuarios_vehiculos.usuario_id = usuarios.id
        WHERE COALESCE(usuarios.activo, 1) = 1
          {filtro_rol}
          AND (
                usuarios.id = ?
                OR LOWER(COALESCE(usuarios.nombre, '')) LIKE ?
                OR LOWER(COALESCE(usuarios.correo, '')) LIKE ?
                OR LOWER(COALESCE(usuarios.cedula, '')) LIKE ?
                OR LOWER(COALESCE(usuarios.rol, '')) LIKE ?
                OR LOWER(COALESCE(usuarios.establecimiento, '')) LIKE ?
          )
        GROUP BY usuarios.id
        ORDER BY
            CASE WHEN usuarios.id = ? THEN 0 ELSE 1 END,
            CASE WHEN LOWER(COALESCE(usuarios.nombre, '')) LIKE ? THEN 0 ELSE 1 END,
            usuarios.nombre COLLATE NOCASE ASC,
            usuarios.id DESC
        LIMIT ?
    """, (
        id_buscado,
        patron,
        patron,
        patron,
        patron,
        patron,
        id_buscado,
        f"{termino.lower()}%",
        limite,
    ))

    resultados = []
    for fila in cursor.fetchall():
        item = dict(fila)
        item["nombre"] = item.get("nombre") or "Usuario sin nombre"
        item["correo"] = item.get("correo") or "Sin correo"
        item["rol"] = item.get("rol") or "USUARIO"
        item["cedula"] = item.get("cedula") or ""
        item["establecimiento"] = item.get("establecimiento") or ""
        item["total_vehiculos"] = int(item.get("total_vehiculos") or 0)
        resultados.append(item)

    return resultados


def listar_notificaciones_enviadas(cursor, remitente_id=None, solo_clientes=False, limite=40):
    """Devuelve mensajes internos enviados para el panel de admin/trabajador."""

    asegurar_tabla_notificaciones_usuario(cursor)
    limite = max(1, min(int(limite or 40), 120))
    condiciones = []
    parametros = []

    if remitente_id:
        condiciones.append("notificaciones_usuario.remitente_id = ?")
        parametros.append(remitente_id)

    if solo_clientes:
        condiciones.append("destinatario.rol = 'USUARIO'")

    where_extra = ""
    if condiciones:
        where_extra = "WHERE " + " AND ".join(condiciones)

    cursor.execute(f"""
        SELECT
            notificaciones_usuario.*,
            destinatario.nombre AS destinatario_nombre,
            destinatario.correo AS destinatario_correo,
            destinatario.rol AS destinatario_rol,
            destinatario.cedula AS destinatario_cedula,
            remitente.nombre AS remitente_nombre,
            remitente.rol AS remitente_rol,
            remitente.establecimiento AS remitente_establecimiento
        FROM notificaciones_usuario
        INNER JOIN usuarios AS destinatario
            ON destinatario.id = notificaciones_usuario.usuario_id
        LEFT JOIN usuarios AS remitente
            ON remitente.id = notificaciones_usuario.remitente_id
        {where_extra}
        ORDER BY datetime(notificaciones_usuario.creado_en) DESC,
                 notificaciones_usuario.id DESC
        LIMIT ?
    """, (*parametros, limite))

    notificaciones = []
    for fila in cursor.fetchall():
        item = dict(fila)
        item["creado_visible"] = core.formatear_fecha_visible(item.get("creado_en"))
        item["tipo"] = normalizar_tipo_notificacion(item.get("tipo"))
        item["prioridad"] = normalizar_prioridad_notificacion(item.get("prioridad"))
        item["destinatario_nombre"] = item.get("destinatario_nombre") or "Usuario eliminado"
        item["destinatario_correo"] = item.get("destinatario_correo") or "Sin correo"
        item["remitente_nombre"] = item.get("remitente_nombre") or "VINOVA"
        notificaciones.append(item)

    return notificaciones

