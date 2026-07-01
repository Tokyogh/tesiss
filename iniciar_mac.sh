#!/bin/bash

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "No existe venv. Creando entorno virtual..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    pip install Flask python-dotenv cloudinary Werkzeug WeasyPrint
fi

python -c "from weasyprint import HTML; HTML(string='<h1>VINOVA OK</h1>').write_pdf('test_weasyprint.pdf')" 2>/dev/null

if [ $? -ne 0 ]; then
    echo ""
    echo "Advertencia: WeasyPrint no pudo generar PDF en este Mac."
    echo "Instala las dependencias con:"
    echo ""
    echo "brew install weasyprint"
    echo ""
    echo "Luego vuelve a ejecutar este archivo."
    echo ""
else
    echo "WeasyPrint funciona correctamente."
fi

python app.py

#esto ejecutalo una sola vez "chmod +x iniciar_mac.sh" sin comillas
#luego para iniciar vinova haz este comando ./iniciar_mac.sh en la terminal de vsc