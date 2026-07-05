from vinova.core import *

@app.errorhandler(413)
def archivo_demasiado_grande(error):
    flash("La imagen es demasiado pesada. Intenta con una imagen más pequeña.", "warning")
    return redirect(request.referrer or "/perfil")
