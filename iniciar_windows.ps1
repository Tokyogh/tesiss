.\venv\Scripts\Activate.ps1

$env:WEASYPRINT_DLL_DIRECTORIES="C:\msys64\ucrt64\bin"
$env:PATH="$PWD\venv\Scripts;C:\msys64\ucrt64\bin;$env:PATH"

python app.py