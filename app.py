from vinova.core import app

# Importar rutas para registrar decoradores de Flask.
from vinova.routes import trabajador  # noqa: F401
from vinova.routes import public_auth  # noqa: F401
from vinova.routes import perfil  # noqa: F401
from vinova.routes import logout  # noqa: F401
from vinova.routes import catalogo  # noqa: F401
from vinova.routes import admin  # noqa: F401
from vinova.routes import facturas  # noqa: F401
from vinova.routes import errores  # noqa: F401


if __name__ == "__main__":
    import os

    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))

    app.run(host=host, port=port, debug=debug)
