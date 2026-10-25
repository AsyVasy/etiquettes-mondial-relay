@echo off
rem Ouvre la fenetre des etiquettes (sans fenetre noire). L'icone du bureau la lance directement.
where pyw >nul 2>&1 && (start "" pyw -3 "%~dp0etiquettes_app.pyw" & exit /b)
start "" pythonw "%~dp0etiquettes_app.pyw"
