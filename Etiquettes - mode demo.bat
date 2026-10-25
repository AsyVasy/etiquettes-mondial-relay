@echo off
rem Mode demonstration : colis inventes, rien n'est envoye a Odoo ni a Mondial Relay (voir demo.py).
where pyw >nul 2>&1 && (start "" pyw -3 "%~dp0etiquettes_app.pyw" --demo & exit /b)
start "" pythonw "%~dp0etiquettes_app.pyw" --demo
