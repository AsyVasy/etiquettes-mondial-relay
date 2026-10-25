"""Étiquettes Mondial Relay — la fenêtre (interface.html affichée par pywebview, fenêtre sans bordure).

Ce fichier ne fait que l'affichage : la logique vient de etiquettes_du_jour.py (colis, Mondial Relay, PDF)
et de reglages.pyw (fichiers .env, test des connexions). Même comportement que etiquettes_fenetre.pyw.
Si pywebview ou WebView2 manque, l'interface classique (tkinter) s'ouvre à la place.
Usage : pyw -3 etiquettes_app.pyw [--odoo odoo.env] [--mr mondialrelay.env] [--bons WH/OUT/1,WH/OUT/2] [--installation] [--demo] [--lecture-seule]
"""
import argparse, base64, csv, ctypes, io, json, os, re, sys, threading
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

POIDS_MAX = 30  # kg : au-delà, c'est sûrement une faute de frappe (1,25 → 125)
# Grille tarifaire facultative (tarifs.json, écrite par l'écran « Grille tarifaire ») : prix HT par pays et tranche de poids.
TRANCHES_G = [500, 1000, 2000, 4000, 10000, 20000, 25000, 30000]  # tranches de l'offre Start (poids jusqu'à, en g)
PAYS_RELAIS = ["FR", "BE", "LU", "NL", "ES", "PT", "DE"]
# Grille publique de l'offre Start relevée sur mondialrelay.fr (onglets « Tarifs et paiement » et « hors domicile »),
# tarifs HT applicables au 7 janvier 2026. France : un prix par palier de colis par mois ; international : prix avant remise.
# La France n'a pas de tranche 20 kg : « jusqu'à 25 kg » couvre 10 à 25 kg, d'où la même valeur sur les deux lignes.
GRILLE_PUBLIQUE = {
    "date": "2026-01-07",
    "paliers": ["0 à 9 colis par mois (prix public)", "10 à 49 colis par mois (-4 %)", "50 à 99 colis par mois (-7 %)",
                "100 à 249 colis par mois (-9 %)", "250 colis et plus par mois (-10 %)"],
    "FR": [[3.42, 3.29, 3.19, 3.12, 3.09], [3.76, 3.61, 3.51, 3.43, 3.40], [5.27, 5.06, 4.91, 4.81, 4.76], [5.59, 5.37, 5.21, 5.10, 5.04],
           [11.13, 10.69, 10.36, 10.14, 10.03], [17.47, 16.78, 16.26, 15.91, 15.74], [17.47, 16.78, 16.26, 15.91, 15.74],
           [19.99, 19.20, 18.60, 18.20, 18.00]],
    "BE": [3.72, 4.82, 6.62, 7.12, 12.93, 19.77, 19.77, 21.00], "LU": [3.72, 4.82, 6.62, 7.12, 12.93, 19.77, 19.77, 21.00],
    "NL": [3.72, 4.82, 6.62, 7.12, 12.93, 19.77, 19.77, 21.00],
    "ES": [5.32, 6.92, 8.42, 9.92, 14.33, 21.87, 21.87, 24.99], "PT": [5.32, 6.92, 8.42, 9.92, 14.33, 21.87, 21.87, 24.99],
    "DE": [5.82, 7.52, 8.62, 11.82, 16.83, 25.77, None, None],
}
TITRE = "Étiquettes Mondial Relay"


def texte_erreur(e):
    if isinstance(e, SystemExit):
        return str(e.code)
    if isinstance(e, FileNotFoundError):
        return f"Fichier introuvable : {Path(e.filename).name}"
    if isinstance(e, KeyError):
        return f"Réglage manquant dans un fichier .env : {e}"
    return f"Erreur : {e}"


class Api:
    """Méthodes appelées depuis interface.html (window.pywebview.api). Chaque appel tourne dans son propre fil.
    L'état interne commence par _ : pywebview n'expose au JavaScript que les attributs sans souligné."""

    def __init__(self, a):
        self._a, self._c, self._fenetre = a, None, None
        self._prets, self._refus, self._relais_changes, self._pdf = [], [], {}, None
        self._verrou = threading.Lock()

    # --- fenêtre ---
    def fermer(self):
        self._fenetre.destroy()

    def reduire(self):
        self._fenetre.minimize()

    def agrandir(self):
        """Bouton « agrandir » de la barre (et double-clic sur la barre) : plein écran de travail ou retour."""
        self._agrandie = not getattr(self, "_agrandie", False)
        (self._fenetre.maximize if self._agrandie else self._fenetre.restore)()

    # --- grille tarifaire (facultative) : estimation, jamais un prix garanti ---
    def _tarifs_chemin(self):
        return Path(self._a.odoo).parent / "tarifs.json"  # à côté des réglages (dossier « demo » en mode démo)

    def tarifs_lire(self):
        vide = {"date": "", "tranches": TRANCHES_G, "pays": {p: [None] * len(TRANCHES_G) for p in PAYS_RELAIS}}
        try:
            data = json.loads(self._tarifs_chemin().read_text(encoding="utf-8"))
            tranches = sorted({int(t) for t in data.get("tranches", []) if int(t) > 0}) or TRANCHES_G
            pays = {code: list(data.get("pays", {}).get(code, []))[:len(tranches)] for code in PAYS_RELAIS}
            for code in pays:
                pays[code] += [None] * (len(tranches) - len(pays[code]))
            return {"date": data.get("date", ""), "tranches": tranches, "pays": pays}
        except (FileNotFoundError, ValueError):
            return vide

    def tarifs_publique(self, palier=0):
        """Grille publique intégrée, France au palier de volume choisi (0 à 4), international avant remise. À vérifier, puis enregistrer."""
        palier = max(0, min(int(palier), 4))
        pays = {"FR": [ligne[palier] for ligne in GRILLE_PUBLIQUE["FR"]]}
        for code in PAYS_RELAIS[1:]:
            pays[code] = list(GRILLE_PUBLIQUE[code])
        return {"date": GRILLE_PUBLIQUE["date"], "tranches": TRANCHES_G, "pays": pays, "paliers": GRILLE_PUBLIQUE["paliers"]}

    def tarifs_enregistrer(self, data):
        """Tranches en grammes (libres, triées, sans doublon) et prix par pays, dans l'ordre des tranches reçues."""
        try:
            brut = [int(round(float(str(t).replace(",", ".")))) for t in data.get("tranches", [])]
            if not brut or len(set(brut)) != len(brut) or any(t <= 0 for t in brut):
                return {"ok": False, "erreur": "Tranches de poids invalides : chaque tranche doit être un poids unique, supérieur à zéro."}
            ordre = sorted(range(len(brut)), key=lambda i: brut[i])
            pays = {}
            for code, prix in data.get("pays", {}).items():
                ligne = []
                for v in list(prix) + [None] * (len(brut) - len(prix)):
                    v = str(v or "").strip().replace(",", ".").replace("€", "")
                    ligne.append(round(float(v), 2) if v else None)
                pays[code] = [ligne[i] for i in ordre]
            self._tarifs_chemin().write_text(json.dumps({"date": data.get("date", ""), "tranches": [brut[i] for i in ordre], "pays": pays},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
            return {"ok": True}
        except (ValueError, OSError) as e:
            return {"ok": False, "erreur": f"Grille non enregistrée : {e}"}

    def lire_fichier_tarifs(self, nom, contenu_b64):
        """Fichier déposé sur l'écran Grille tarifaire → texte brut, que la page analyse comme un tableau collé."""
        try:
            octets = base64.b64decode(contenu_b64.split(",", 1)[-1])
            suffixe = Path(nom).suffix.lower()
            if suffixe == ".pdf":
                from pypdf import PdfReader
                texte = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(octets)).pages)
                if not texte.strip():
                    return {"erreur": "Ce PDF ne contient pas de texte lisible (image scannée ?). Collez le tableau à la main."}
                return {"texte": texte}
            if suffixe in (".csv", ".txt", ".tsv", ""):
                for enc in ("utf-8-sig", "cp1252"):
                    try:
                        return {"texte": octets.decode(enc)}
                    except UnicodeDecodeError:
                        continue
                return {"erreur": "Impossible de lire le texte de ce fichier."}
            if suffixe in (".xlsx", ".xls", ".ods"):
                return {"erreur": "Les classeurs Excel ne sont pas lus directement : enregistrez la feuille au format CSV, ou copiez-collez le tableau."}
            return {"erreur": f"Format « {suffixe or 'inconnu'} » non pris en charge : PDF, CSV ou texte."}
        except Exception as e:
            return {"erreur": f"Lecture impossible : {e}"}

    def _prix(self, pays, grammes, grille=None):
        """Prix HT estimé d'une étiquette, ou None si la grille ne couvre pas ce cas."""
        grille = grille or self.tarifs_lire()
        ligne = grille["pays"].get(pays) or []
        for i, maxi in enumerate(grille["tranches"]):
            if grammes <= maxi:
                return ligne[i] if i < len(ligne) else None
        return None

    def info(self):
        return {"installation": self._a.installation, "complet": self._a.odoo != str(ICI / "odoo.env") or rg.complet(),
                "lecture": self._a.lecture_seule}

    # --- colis ---
    def demarrer(self):
        try:
            with self._verrou:
                self._c = mr.ouvrir(self._a.odoo, self._a.mr)
            return {"ok": True, "reel": self._c["reel"], "db": self._c["o"].db}
        except BaseException as e:  # SystemExit des garde-fous compris
            self._c = None
            return {"ok": False, "erreur": texte_erreur(e)}

    def lister(self):
        try:
            with self._verrou:
                self._prets, self._refus = mr.selection(self._c, self._a.bons, dict(self._relais_changes))
                self._frais = self._frais_port([b for b, _, _ in self._prets])
            return {"ok": True,
                    "prets": [{"bon": b["name"], "commande": b["origin"] or b["name"], "client": p["Dest_Ad1"][:28],
                               "relais_num": p["LIV_Rel"], "relais": relais, "change": b["name"] in self._relais_changes,
                               "facture_ttc": self._frais.get(b["name"], {}).get("ttc"), "facture_ht": self._frais.get(b["name"], {}).get("ht")}
                              for b, p, relais in self._prets],
                    "refus": [{"bon": b["name"], "commande": b["origin"] or "", "motif": why} for b, why in self._refus]}
        except BaseException as e:
            return {"ok": False, "erreur": texte_erreur(e)}

    def _frais_port(self, bons):
        """{n° de bon: {"ht", "ttc"}} d'après la ligne de livraison de la commande Odoo. Vide si les ventes ne sont pas lisibles."""
        if getattr(self, "_sans_ventes", False) or not bons:
            return {}
        try:
            o = self._c["o"]
            picks = o("stock.picking", "search_read", [["id", "in", [b["id"] for b in bons]]], fields=["name", "sale_id"])
            commande = {p["sale_id"][0]: p["name"] for p in picks if p.get("sale_id")}
            if not commande:
                return {}
            lignes = o("sale.order.line", "search_read", [["order_id", "in", list(commande)], ["is_delivery", "=", True]],
                       fields=["order_id", "price_subtotal", "price_total"])
            frais = {}
            for l in lignes:
                bon = commande.get(l["order_id"][0])
                if bon:
                    f = frais.setdefault(bon, {"ht": 0.0, "ttc": 0.0})
                    f["ht"] += l["price_subtotal"]; f["ttc"] += l["price_total"]
            return frais
        except Exception:
            self._sans_ventes = True  # pas le droit de lire les ventes : on n'affiche rien, sans gêner le reste
            return {}

    def _ligne(self, bon):
        return next(l for l in self._prets if l[0]["name"] == bon)

    def changer_relais(self, bon, valeur):
        valeur = valeur.strip().upper()
        if not re.fullmatch(r"([A-Z]{2}-)?\d{6}", valeur):
            return {"ok": False, "info": "Il faut le numéro à 6 chiffres du point relais, ex. 036354."}
        try:
            b, p, _ = self._ligne(bon)
            with self._verrou:
                ok, info = mr.changer_relais(self._c, p, valeur)
            if not ok:
                return {"ok": False, "info": info}
            self._relais_changes[bon] = valeur
            self._prets = [(bb, pp, info if bb["name"] == bon else rr) for bb, pp, rr in self._prets]
            return {"ok": True, "info": info, "num": p["LIV_Rel"]}
        except BaseException as e:
            return {"ok": False, "info": texte_erreur(e)}

    def verifier_poids(self, lignes):
        """[{bon, poids}] → kg par bon et liste des bons en faute (vide, illisible, ≤ 0 ou > POIDS_MAX)."""
        kg, fautes, prix, grille = {}, [], {}, self.tarifs_lire()
        for l in lignes:
            try:
                v = mr.poids_kg(l["poids"])
                if v > POIDS_MAX:
                    raise ValueError
                kg[l["bon"]] = v
                pays = next((p["LIV_Rel_Pays"] for b, p, _ in self._prets if b["name"] == l["bon"]), "FR")
                prix[l["bon"]] = self._prix(pays, int(round(v * 1000)), grille)
            except ValueError:
                fautes.append(l["bon"])
        return {"kg": kg, "fautes": fautes, "prix": prix, "grille_date": grille["date"]}

    def creer(self, lignes):
        if self._a.lecture_seule:
            return {"ok": False, "erreur": "Mode lecture seule : aucune étiquette n'est créée. Relancez l'outil par l'icône du Bureau pour créer."}
        if not getattr(self._c["o"], "base_prod", "") and self._c["o"].db != "demo":
            # sans base de production déclarée, l'outil serait en simulation sur une base peut-être réelle : on refuse
            return {"ok": False, "erreur": "Aucune base de production déclarée dans Réglages : création refusée. "
                                           "Renseignez « Base de production » (ou laissez-la différente de la base connectée pour une simulation assumée)."}
        v = self.verifier_poids(lignes)
        if v["fautes"]:
            return {"ok": False, "erreur": "Poids manquant ou pas compris."}
        try:
            prets = []
            for l in lignes:
                b, p, relais = self._ligne(l["bon"])
                mr.mettre_poids(p, v["kg"][l["bon"]])
                prets.append((b, p, relais))
            with self._verrou:
                total, faits, echecs = mr.creer(self._c, prets, self._a.sortie, dire=lambda *_: None)
            self._pdf = str(total) if total else None
            if total:
                # complément pour l'Historique (pays du relais et prix estimé par bon) : fichier à part, le moteur n'y touche pas
                grille = self.tarifs_lire()
                complement = {b["name"]: {"pays": p["LIV_Rel_Pays"], "prix": self._prix(p["LIV_Rel_Pays"], int(p["Poids"]), grille),
                                          "facture_ttc": getattr(self, "_frais", {}).get(b["name"], {}).get("ttc")}
                              for b, p, _ in prets}
                (total.parent / "complement.json").write_text(json.dumps(complement, ensure_ascii=False), encoding="utf-8")
                os.startfile(total)  # ouvre le PDF pour l'imprimer
            return {"ok": True, "pdf": self._pdf, "faits": faits,
                    "echecs": [{"bon": b["name"], "commande": b["origin"] or b["name"], "motif": why} for b, why in echecs]}
        except BaseException as e:
            return {"ok": False, "erreur": texte_erreur(e)}

    def ouvrir_pdf(self):
        if self._pdf and Path(self._pdf).exists():
            os.startfile(self._pdf)

    # --- historique : lecture du dossier « sortie » écrit par creer() (un sous-dossier AAAAMMJJ-HHMM par création) ---
    def historique(self):
        sortie = Path(self._a.sortie)
        creations = []
        for d in sorted(sortie.iterdir(), reverse=True) if sortie.is_dir() else []:
            if not (d.is_dir() and re.fullmatch(r"\d{8}-\d{4}", d.name)):
                continue
            recap, pdf = d / f"recap-{d.name}.csv", d / f"etiquettes-{d.name}.pdf"
            try:
                complement = json.loads((d / "complement.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                complement = {}
            lignes = []
            if recap.exists():
                with open(recap, encoding="utf-8-sig", newline="") as f:
                    for r in csv.DictReader(f, delimiter=";"):
                        fichier = d / f"{r.get('bon', '').replace('/', '-')}.pdf"
                        comp = complement.get(r.get("bon", ""), {})
                        lignes.append({**r, "fichier": str(fichier) if fichier.exists() else None,
                                       "prix": comp.get("prix"), "facture_ttc": comp.get("facture_ttc")})
            creations.append({"stamp": d.name, "dossier": str(d), "pdf": str(pdf) if pdf.exists() else None, "lignes": lignes})
        return creations

    def ouvrir_fichier(self, chemin):
        """Ouvre un PDF ou un dossier de l'historique (seulement à l'intérieur du dossier « sortie »)."""
        p = Path(chemin).resolve()
        if Path(self._a.sortie).resolve() in p.parents and p.exists():
            os.startfile(p)

    # --- réglages (même logique que la fenêtre reglages.pyw) ---
    def reglages_lire(self):
        v = {**rg.lire(rg.ODOO_ENV), **rg.lire(rg.MR_ENV)}
        if not v.get("MR_DEPUIS"):
            v["MR_DEPUIS"] = rg.date.today().isoformat()
        return {"valeurs": v, "odoo": rg.CHAMPS_ODOO, "mr": rg.CHAMPS_MR}

    def reglages_verifier(self, v):
        return rg.verifier(v)

    def reglages_tester(self, v):
        return [[ok, t] for ok, t in rg.tester(v)]

    def reglages_enregistrer(self, v):
        try:
            rg.ecrire(v)
            return {"ok": True}
        except BaseException as e:
            return {"ok": False, "erreur": texte_erreur(e)}


def arrondir(fenetre):
    """Coins arrondis Windows 11 sur la fenêtre sans bordure (DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND)."""
    try:
        natif = getattr(fenetre, "native", None)
        hwnd = natif.Handle.ToInt32() if natif is not None else ctypes.windll.user32.FindWindowW(None, TITRE)
        if hwnd:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except Exception:
        pass


def deja_ouverte():
    """Une seule fenêtre à la fois : verrou Windows nommé. Si l'outil tourne déjà, ramène sa fenêtre devant et répond True."""
    ctypes.windll.kernel32.CreateMutexW(None, False, r"Local\EtiquettesMondialRelay")
    if ctypes.windll.kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = ctypes.windll.user32.FindWindowW(None, TITRE)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE (sort aussi de la réduction)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True


def interface_classique(a):
    """Secours sans pywebview / WebView2 : les fenêtres tkinter existantes. Le mode lecture seule y est respecté."""
    if a.installation:
        rg.Reglages(True).mainloop()
    else:
        if getattr(a, "lecture_seule", False):
            def refus(*_, **__):
                raise SystemExit("Mode lecture seule : aucune étiquette n'est créée.")
            mr.creer = refus
        import etiquettes_fenetre
        etiquettes_fenetre.Fenetre(a).mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odoo", default=str(ICI / "odoo.env"))
    ap.add_argument("--mr", default=str(ICI / "mondialrelay.env"))
    ap.add_argument("--bons", default="", help="liste de bons précis, au lieu de la sélection automatique")
    ap.add_argument("--sortie", default=str(ICI / "sortie"))
    ap.add_argument("--installation", action="store_true", help="lancée par l'installateur : ouvre les réglages, se ferme après")
    ap.add_argument("--demo", action="store_true", help="mode démonstration : données locales, rien n'est envoyé (voir demo.py)")
    ap.add_argument("--lecture-seule", action="store_true", help="vraie base, mais création d'étiquettes bloquée (pour tester sans rien payer)")
    a = ap.parse_args()
    if a.demo:
        import demo
        demo.activer(a)
    if deja_ouverte():
        return
    try:
        import webview
    except ModuleNotFoundError:
        return interface_classique(a)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    api = Api(a)
    api._fenetre = webview.create_window(TITRE, url=str(ICI / "interface.html"), js_api=api, width=1060, height=700,
                                        min_size=(900, 620), frameless=True, easy_drag=False, shadow=True,
                                        background_color="#F5F5F7", text_select=False)
    try:
        webview.start(arrondir, api._fenetre, private_mode=True)
    except Exception:
        interface_classique(a)


try:
    import etiquettes_du_jour as mr  # noqa: E402
    import reglages as rg  # noqa: E402
except ModuleNotFoundError as e:  # pypdf absent : message au lieu d'un double-clic sans effet
    import tkinter as tk
    from tkinter import messagebox
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror(TITRE, f"Il manque le composant « {e.name} ».\n\nRelancez « Installer (une seule fois).bat »,\n"
                                "ou contactez l'administrateur de l'outil.")
    raise SystemExit(1)

if __name__ == "__main__":
    main()
