@echo off
setlocal
cd /d "%~dp0"
python -c "import sys, tkinter; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
    python -c "import subprocess,sys; subprocess.Popen([sys.executable,sys.argv[1]], creationflags=0x08000000)" "%~dp0iniciar.pyw"
    exit /b
)
py -3 -c "import sys, tkinter; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import subprocess,sys; subprocess.Popen([sys.executable,sys.argv[1]], creationflags=0x08000000)" "%~dp0iniciar.pyw"
    exit /b
)
echo Instale o Python 3.10 ou superior com Tkinter e a opcao Add Python to PATH.
echo Depois abra este arquivo novamente.
echo https://www.python.org/downloads/windows/
pause
