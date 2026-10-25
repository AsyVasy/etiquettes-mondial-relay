@echo off
rem Lecture seule : vraie base Odoo et vrai compte Mondial Relay, mais aucune etiquette ne peut etre creee (rien n'est paye).
where pyw >nul 2>&1 && (start "" pyw -3 "%~dp0etiquettes_app.pyw" --lecture-seule & exit /b)
start "" pythonw "%~dp0etiquettes_app.pyw" --lecture-seule
