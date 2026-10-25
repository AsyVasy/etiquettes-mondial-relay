"""Rend un écran de interface.html en PNG avec Edge sans fenêtre, sur un faux pont pywebview (mock.js).

Usage : py -3 rendu_maquette.py <scenario> [sortie.png]
Scénarios (voir mock.js) : colis, colis-survol, colis-decoche, confirmation, historique, reglages, reglages-aide,
reglages-echec, reglages-points, tarifs.
Sert à vérifier l'interface sans ouvrir de fenêtre à l'écran (utile quand une application plein écran tourne).
"""
import subprocess, sys, tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
EDGE = next((p for p in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                         Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")) if p.exists()), None)


def main():
    if len(sys.argv) < 2 or EDGE is None:
        print(__doc__ if EDGE else "Edge introuvable."); return 1
    scenario = sys.argv[1]
    sortie = Path(sys.argv[2]) if len(sys.argv) > 2 else ICI / f"rendu-{scenario}.png"
    src = (ICI.parent / "interface.html").read_text(encoding="utf-8")
    mock = (ICI / "mock.js").read_text(encoding="utf-8")
    page = src.replace('<html lang="fr">', f'<html lang="fr" data-scenario="{scenario}">', 1).replace("<script>", "<script>" + mock + "</script>\n<script>", 1)
    tmp = Path(tempfile.mkdtemp()) / f"{scenario}.html"
    tmp.write_text(page, encoding="utf-8")
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--window-size=1060,650", "--virtual-time-budget=4000", f"--screenshot={sortie}", tmp.as_uri()],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print(sortie if sortie.exists() else "rendu non produit")


if __name__ == "__main__":
    sys.exit(main())
