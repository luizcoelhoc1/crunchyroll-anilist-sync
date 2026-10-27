@echo off
setlocal
cd /d "%~dp0"
echo Instalando ou atualizando Pillow para avatares JPEG e WebP...
python -c "import sys, tkinter; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
    python -m pip install --upgrade Pillow
) else (
    py -3 -m pip install --upgrade Pillow
)
echo.
echo Feche e abra o sincronizador novamente depois da instalacao.
pause
