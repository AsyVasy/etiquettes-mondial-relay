@echo off
chcp 65001 >nul
title Installation - Etiquettes Mondial Relay
setlocal
cd /d "%~dp0"
set "PYVER=3.13.17"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-arm64.exe"

echo ==============================================
echo   Etiquettes Mondial Relay - installation
echo ==============================================
echo.
echo Etape 1 sur 4 : Python
call :trouver_python
if defined PY goto python_ok
echo   Python n'est pas installe : telechargement depuis python.org (30 Mo)...
set "INST=%TEMP%\python-%PYVER%-installateur.exe"
curl.exe -L -# -o "%INST%" "%PYURL%" || powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYURL%' -OutFile '%INST%'"
if not exist "%INST%" (
  echo   Echec du telechargement. Verifiez la connexion internet, puis relancez ce fichier.
  goto fin_erreur
)
echo   Installation de Python %PYVER% (1 a 2 minutes, patientez, rien ne s'affiche)...
start /wait "" "%INST%" /quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_launcher=1 Include_tcltk=1 Include_pip=1 Include_test=0 Include_doc=0 Shortcuts=0
del "%INST%" >nul 2>&1
call :trouver_python
if not defined PY (
  echo   Python ne repond pas apres l'installation. Redemarrez le PC, puis relancez ce fichier.
  goto fin_erreur
)
:python_ok
echo   Python trouve :
%PY% --version
%PY% -c "import tkinter" >nul 2>&1 || (
  echo   Python est installe sans tkinter : reinstallez Python depuis python.org en laissant "tcl/tk" coche.
  goto fin_erreur
)

echo.
echo Etape 2 sur 4 : bibliotheques (pypdf, pywebview)
%PY% -m pip install --quiet --disable-pip-version-check --no-warn-script-location pypdf pywebview || (
  echo   Echec de l'installation des bibliotheques. Verifiez la connexion internet, puis relancez ce fichier.
  goto fin_erreur
)
%PY% -c "import pypdf, webview" >nul 2>&1 || (
  echo   Bibliotheques installees mais introuvables. Contactez l'administrateur de l'outil.
  goto fin_erreur
)
echo   pypdf et pywebview OK

echo.
echo Etape 3 sur 4 : icones du bureau
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Etiquettes Mondial Relay.lnk'); $s.TargetPath='%PYW%'; $s.Arguments=[char]34+'%~dp0etiquettes_app.pyw'+[char]34; $s.WorkingDirectory='%~dp0'; $s.Save(); if (Test-Path -LiteralPath '%~dp0Odoo - colis Mondial Relay.url') { Copy-Item -LiteralPath '%~dp0Odoo - colis Mondial Relay.url' -Destination $d -Force }"
echo   Icones creees

echo.
echo Etape 4 sur 4 : reglages (identifiants Odoo et Mondial Relay)
echo   Une fenetre s'ouvre : remplissez-la, cliquez sur "Tester les connexions", puis "Enregistrer".
start /wait "" "%PYW%" "%~dp0etiquettes_app.pyw" --installation

echo.
echo Termine. Icone "Etiquettes Mondial Relay" sur le Bureau.
echo Pour changer un reglage plus tard : "Reglages" en haut de la fenetre de l'outil.
pause
exit /b

:fin_erreur
echo.
echo Installation interrompue.
pause
exit /b 1

:trouver_python
rem Cherche Python 3 : lanceur py, puis python, puis l'installation par defaut de python.org pour cet utilisateur.
set "PY="
set "PYW="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set PY="%%d\python.exe"
if not defined PY exit /b
rem pythonw.exe (lance les fenetres sans console) a cote du python trouve
%PY% -c "import os,sys;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\etiquettesmr-pyw.txt" 2>nul
set /p PYW=<"%TEMP%\etiquettesmr-pyw.txt"
del "%TEMP%\etiquettesmr-pyw.txt" >nul 2>&1
if not exist "%PYW%" set "PY="
exit /b
