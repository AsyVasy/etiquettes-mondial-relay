@echo off
chcp 65001 >nul
title Etiquettes Mondial Relay - version console
where py >nul 2>&1 && (set PY=py -3) || (set PY=python)
%PY% -I -X utf8 "%~dp0etiquettes_du_jour.py" --odoo "%~dp0odoo.env" --mr "%~dp0mondialrelay.env"
echo.
echo Appuyez sur une touche pour fermer cette fenetre.
pause >nul
