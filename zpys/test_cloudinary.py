from dotenv import load_dotenv
import os
import cloudinary
import cloudinary.uploader
from pathlib import Path

load_dotenv()

cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")

print("Cloud name:", cloud_name)
print("API key cargada:", "Sí" if api_key else "No")
print("API secret cargada:", "Sí" if api_secret else "No")

if not cloud_name or not api_key or not api_secret:
    raise ValueError("No se cargaron bien las variables del archivo .env")

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

ruta_imagen = Path("static/img/fondo.png")

if not ruta_imagen.exists():
    raise FileNotFoundError(f"No existe la imagen: {ruta_imagen}")

resultado = cloudinary.uploader.upload(
    str(ruta_imagen),
    folder="vinova/perfiles/test"
)

print("Imagen subida correctamente.")
print("URL:", resultado["secure_url"])