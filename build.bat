@echo off
REM Crea dist\Anonimizzatore.exe (un solo file, senza console)
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :err

REM Le opzioni (un solo file, senza console, esclusione di pymupdf.layout) sono in
REM Anonimizzatore.spec, condiviso con la build per macOS.
python -m PyInstaller --noconfirm --clean Anonimizzatore.spec || goto :err

echo.
echo Fatto: dist\Anonimizzatore.exe
pause
exit /b 0

:err
echo.
echo Errore durante la build.
pause
exit /b 1
