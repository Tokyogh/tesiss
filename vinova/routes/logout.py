from vinova.core import *

@app.route("/logout", methods=["POST"])
def logout():

    conexion = conectar_db()
    try:
        registrar_auditoria(
            conexion,
            "Cierre de sesión",
            "usuario",
            session.get("usuario_id"),
            {"usuario": session.get("usuario"), "rol": session.get("rol")}
        )
        conexion.commit()
    except Exception as error:
        conexion.rollback()
        print("Advertencia: no se pudo auditar cierre de sesión:", error)
    finally:
        conexion.close()

    session.clear()

    return redirect("/")
