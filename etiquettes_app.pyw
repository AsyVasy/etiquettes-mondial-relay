"""Étiquettes Mondial Relay — la fenêtre (interface.html affichée par pywebview, fenêtre sans bordure).

Ce fichier ne fait que l'affichage : la logique vient de etiquettes_du_jour.py (colis, Mondial Relay, PDF)
et de reglages.pyw (fichiers .env, test des connexions). Même comportement que etiquettes_fenetre.pyw.
Si pywebview ou WebView2 manque, l'interface classique (tkinter) s'ouvre à la place.
Usage : pyw -3 etiquettes_app.pyw [--odoo odoo.env] [--mr mondialrelay.env] [--bons WH/OUT/1,WH/OUT/2] [--installation] [--demo] [--lecture-seule]
"""
import argparse, base64, csv, ctypes, io, json, os, platform, re, sys, threading
from datetime import datetime, timedelta, timezone
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
VERSION = "2026-10-28"
JOURNAL_LIGNES = 400  # lignes gardées dans journal.log


def journal(a, texte):
    """Journal borné, à côté des réglages (dossier « demo » en mode démo) : date, heure, texte. Jamais de clé."""
    try:
        chemin = Path(a.odoo).parent / "journal.log"
        lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
        lignes.append(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texte}")
        chemin.write_text("\n".join(lignes[-JOURNAL_LIGNES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def ecrire_pdf(chemin, lignes, titre):
    """PDF texte de plusieurs pages (Courier, sans bibliothèque) : lignes = textes ou (texte, gras)."""
    def esc(s):
        s = str(s).replace("→", "->").replace("…", "...").replace("–", "-")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    pages, page, y = [], [f"BT /F2 14 Tf 40 800 Td ({esc(titre)}) Tj ET"], 780
    for l in lignes:
        texte, gras = l if isinstance(l, tuple) else (l, False)
        for m in [texte[i:i + 95] for i in range(0, len(texte), 95)] or [""]:
            if y < 50:
                pages.append(page); page, y = [], 800
            y -= 12
            if m:
                page.append(f"BT /{'F2' if gras else 'F1'} 9 Tf 40 {y} Td ({esc(m)}) Tj ET")
    pages.append(page)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for flux in pages:
        contenu = "\n".join(flux).encode("cp1252", "replace")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                    b"/Contents " + str(len(objs) + 2).encode() + b" 0 R >>")
        kids.append(len(objs))
        objs.append(b"<< /Length " + str(len(contenu)).encode() + b" >>\nstream\n" + contenu + b"\nendstream")
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(f"{k} 0 R".encode() for k in kids) + b"] /Count " + str(len(kids)).encode() + b" >>"
    out, pos = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        pos.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{p:010d} 00000 n \n".encode() for p in pos)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(chemin).write_bytes(out)


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

    def _j(self, texte):
        journal(self._a, texte)

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
            self._j(f"démarrage v{VERSION} : base « {self._c['o'].db} », " + ("PRODUCTION" if self._c["reel"] else "simulation")
                    + (", lecture seule" if self._a.lecture_seule else ""))
            return {"ok": True, "reel": self._c["reel"], "db": self._c["o"].db}
        except BaseException as e:  # SystemExit des garde-fous compris
            self._c = None
            self._j(f"démarrage impossible : {texte_erreur(e)}")
            return {"ok": False, "erreur": texte_erreur(e)}

    def lister(self):
        try:
            with self._verrou:
                self._prets, self._refus = mr.selection(self._c, self._a.bons, dict(self._relais_changes))
                self._frais = self._frais_port([b for b, _, _ in self._prets])
            self._j(f"liste : {len(self._prets)} à étiqueter, {len(self._refus)} refusé(s)" + "".join(f" | {b['name']} : {why}" for b, why in self._refus))
            return {"ok": True,
                    "prets": [{"bon": b["name"], "commande": b["origin"] or b["name"], "client": p["Dest_Ad1"][:28],
                               "relais_num": p["LIV_Rel"], "relais": relais, "change": b["name"] in self._relais_changes,
                               "facture_ttc": self._frais.get(b["name"], {}).get("ttc"), "facture_ht": self._frais.get(b["name"], {}).get("ht")}
                              for b, p, relais in self._prets],
                    "refus": [{"bon": b["name"], "commande": b["origin"] or "", "motif": why} for b, why in self._refus]}
        except BaseException as e:
            self._j(f"liste : erreur {texte_erreur(e)}")
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
            self._j(f"relais {bon} -> {valeur} : " + ("OK" if ok else info))
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
            tape = {l["bon"]: str(l.get("poids", "")).strip() for l in lignes}
            self._j(f"création demandée : {len(prets)} colis, " + ", ".join(
                f"{b['name']} tapé « {tape.get(b['name'], '')} » -> {p['Poids']} g (Odoo {b.get('shipping_weight') or b.get('weight') or 0} kg)" for b, p, _ in prets))
            with self._verrou:
                total, faits, echecs = mr.creer(self._c, prets, self._a.sortie, dire=lambda *_: None)
            self._j(f"création : {len(faits)} faite(s), {len(echecs)} refus" + "".join(f" | {f['bon']} -> n° {f['n_colis']}" for f in faits)
                    + "".join(f" | {b['name']} : {why}" for b, why in echecs))
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
            self._j(f"création : erreur {texte_erreur(e)}")
            return {"ok": False, "erreur": texte_erreur(e)}

    def ouvrir_pdf(self):
        if self._pdf and Path(self._pdf).exists():
            os.startfile(self._pdf)

    # --- historique : les étiquettes connues d'Odoo (30 jours) fusionnées avec les créations de ce poste (dossier « sortie ») ---
    HISTORIQUE_JOURS = 30

    def _creations_locales(self):
        """Créations de ce poste : {bon: ligne} et liste des refus, d'après les dossiers AAAAMMJJ-HHMMSS de « sortie »."""
        sortie, lignes, refus = Path(self._a.sortie), {}, []
        for d in sorted(sortie.iterdir(), reverse=True) if sortie.is_dir() else []:
            if not (d.is_dir() and re.fullmatch(r"\d{8}-\d{4}(\d{2})?", d.name)):
                continue
            s = d.name + ("00" if len(d.name) == 13 else "")
            date = f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]}:{s[13:15]}"
            try:
                complement = json.loads((d / "complement.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                complement = {}
            for nom, cible in (("recap", lignes), ("refus", refus)):
                f = d / f"{nom}-{d.name}.csv"
                if not f.exists():
                    continue
                with open(f, encoding="utf-8-sig", newline="") as fh:
                    for r in csv.DictReader(fh, delimiter=";"):
                        bon = r.get("bon", "")
                        if nom == "refus":
                            refus.append({"date": date, "bon": bon, "commande": r.get("commande", ""), "stat": r.get("stat", ""),
                                          "poids_g": r.get("poids_g", ""), "motif": r.get("motif", "")})
                        elif bon not in lignes:  # la création la plus récente l'emporte
                            fichier, pdf = d / f"{bon.replace('/', '-')}.pdf", d / f"etiquettes-{d.name}.pdf"
                            comp = complement.get(bon, {})
                            lignes[bon] = {"date": date, "commande": r.get("commande", ""), "bon": bon, "client": r.get("client", ""),
                                           "relais": r.get("relais", ""), "n_colis": r.get("n_colis", ""), "poids_g": r.get("poids_g", ""),
                                           "prix": comp.get("prix"), "facture_ttc": comp.get("facture_ttc"), "ce_poste": True,
                                           "fichier": str(fichier) if fichier.exists() else None, "dossier": str(d),
                                           "pdf_global": str(pdf) if pdf.exists() else None}
        return lignes, refus

    def _etiquettes_odoo(self):
        """Bons Mondial Relay validés depuis HISTORIQUE_JOURS jours qui portent un n° de colis, d'où qu'il vienne : {bon: ligne}."""
        o = self._c["o"]
        depuis = (datetime.now(timezone.utc) - timedelta(days=self.HISTORIQUE_JOURS)).strftime("%Y-%m-%d %H:%M:%S")
        picks = o("stock.picking", "search_read", [["carrier_id.is_mondialrelay", "=", True], ["carrier_tracking_ref", "!=", False], ["date_done", ">=", depuis]],
                  fields=["name", "origin", "partner_id", "carrier_tracking_ref", "date_done"], order="date_done desc", limit=300)
        ids = sorted({p["partner_id"][0] for p in picks if p.get("partner_id")})
        parts = {r["id"]: r for r in o("res.partner", "read", ids, fields=["name", "parent_id"])} if ids else {}
        lignes = {}
        for p in picks:
            pr = parts.get(p["partner_id"][0]) if p.get("partner_id") else None
            client = (pr["parent_id"][1] if pr and pr.get("parent_id") else (pr["name"] if pr else ""))
            relais = pr["name"] if pr and pr.get("parent_id") else ""
            try:  # Odoo donne l'heure en UTC
                date = datetime.strptime(p["date_done"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                date = p.get("date_done") or ""
            lignes[p["name"]] = {"date": date, "commande": p.get("origin") or "", "bon": p["name"], "client": client, "relais": relais,
                                 "n_colis": p["carrier_tracking_ref"], "poids_g": "", "prix": None, "facture_ttc": None, "ce_poste": False,
                                 "fichier": None, "dossier": None, "pdf_global": None}
        return lignes

    def historique(self):
        """Une ligne par bon : Odoo (toutes les étiquettes) enrichi par ce poste (PDF local, coût, facturé) ; refus de ce poste à part."""
        locales, refus = self._creations_locales()
        odoo, erreur = {}, ""
        if self._c:
            try:
                odoo = self._etiquettes_odoo()
            except BaseException as e:
                erreur = texte_erreur(e); self._j(f"historique : Odoo illisible, {erreur}")
        else:
            erreur = "non connecté à Odoo"
        lignes = {}
        for bon, l in odoo.items():
            lignes[bon] = l
        for bon, l in locales.items():
            if bon in lignes:
                lignes[bon].update({k: v for k, v in l.items() if k in ("fichier", "dossier", "pdf_global", "prix", "facture_ttc", "poids_g", "ce_poste")})
                if not lignes[bon]["relais"]:
                    lignes[bon]["relais"] = l["relais"]
            else:
                lignes[bon] = l
        tri = sorted(lignes.values(), key=lambda l: l["date"], reverse=True)
        return {"lignes": tri, "refus": sorted(refus, key=lambda r: r["date"], reverse=True), "jours": self.HISTORIQUE_JOURS,
                "odoo": bool(odoo) or (self._c is not None and not erreur), "erreur": erreur}

    def suivi(self, num):
        """Suivi Mondial Relay d'un n° de colis (gratuit)."""
        if not num or (str(num).startswith("TEST") and not self._a.demo):
            return {"ok": True, "stat": "", "etat": "Simulation", "detail": "aucun colis réel", "evenements": []}
        try:
            return mr.suivi(self._c["ens"], self._c["cle"], str(num))
        except BaseException as e:
            return {"ok": False, "stat": "", "etat": texte_erreur(e)}

    def _pdf_colis(self, num, fichier=None):
        """Chemin du PDF d'un colis : le fichier local s'il existe, sinon celui redemandé à Mondial Relay (gratuit), gardé dans sortie/recuperees.
        Renvoie (chemin, local) ou lève une erreur lisible."""
        sortie = Path(self._a.sortie).resolve()
        if fichier:
            p = Path(fichier).resolve()
            if sortie in p.parents and p.exists():
                return p, True
        if not num or str(num).startswith("TEST"):
            raise RuntimeError("Pas de PDF : étiquette de simulation, ou fichier local supprimé.")
        dossier = sortie / "recuperees"; dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"etiquette-{num}.pdf"
        if chemin.exists() and chemin.stat().st_size > 0:  # déjà redemandé une fois
            return chemin, True
        data = mr.etiquette_pdf(self._c["ens"], self._c["cle"], str(num), self._c["mr"].get("MR_FORMAT", "A4"))
        chemin.write_bytes(data)
        self._j(f"PDF redemandé à Mondial Relay : n° {num} -> {chemin.name}")
        return chemin, False

    def etiquette_pdf(self, num, fichier=None):
        """Ouvre l'étiquette d'un colis (PDF local, sinon redemandé à Mondial Relay)."""
        try:
            chemin, local = self._pdf_colis(num, fichier)
            os.startfile(chemin)
            return {"ok": True, "chemin": str(chemin), "local": local}
        except BaseException as e:
            self._j(f"PDF n° {num} : erreur {texte_erreur(e)}")
            return {"ok": False, "erreur": texte_erreur(e)}

    def etiquettes_lot(self, colis):
        """Un seul PDF avec les étiquettes sélectionnées (chacune : locale, sinon redemandée), dans sortie/recuperees, ouvert pour l'imprimer.
        colis : [{"n_colis", "fichier", "bon"}]. Les étiquettes introuvables sont listées dans « echecs », les autres sont quand même imprimées."""
        try:
            from pypdf import PdfReader, PdfWriter
            pdf, faits, echecs = PdfWriter(), [], []
            for c in colis or []:
                num, bon = str(c.get("n_colis") or ""), c.get("bon") or ""
                try:
                    chemin, _ = self._pdf_colis(num, c.get("fichier"))
                    for page in PdfReader(str(chemin)).pages:
                        pdf.add_page(page)
                    faits.append(bon)
                except BaseException as e:
                    echecs.append({"bon": bon, "n_colis": num, "motif": texte_erreur(e)})
            if not faits:
                raise RuntimeError("Aucune étiquette à imprimer : " + " ; ".join(f"{e['bon']} : {e['motif']}" for e in echecs))
            dossier = Path(self._a.sortie).resolve() / "recuperees"; dossier.mkdir(parents=True, exist_ok=True)
            chemin = dossier / f"selection-{datetime.now():%Y%m%d-%H%M%S}.pdf"
            with open(chemin, "wb") as f:
                pdf.write(f)
            self._j(f"impression multiple : {len(faits)} étiquette(s) -> {chemin.name}" + "".join(f" | {e['bon']} : {e['motif']}" for e in echecs))
            os.startfile(chemin)
            return {"ok": True, "chemin": str(chemin), "n": len(faits), "echecs": echecs}
        except BaseException as e:
            self._j(f"impression multiple : erreur {texte_erreur(e)}")
            return {"ok": False, "erreur": texte_erreur(e)}

    def ouvrir_fichier(self, chemin):
        """Ouvre un PDF ou un dossier de l'historique (seulement à l'intérieur du dossier « sortie »)."""
        p, sortie = Path(chemin).resolve(), Path(self._a.sortie).resolve()
        if (p == sortie or sortie in p.parents) and p.exists():
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
        res = rg.tester(v)
        self._j("test des connexions : " + " | ".join(("OK " + t.split(" : ")[0]) if ok else ("ÉCHEC " + t) for ok, t in res))
        return [[ok, t] for ok, t in res]

    def reglages_enregistrer(self, v):
        try:
            rg.ecrire(v)
            self._j("réglages enregistrés")
            return {"ok": True}
        except BaseException as e:
            self._j(f"réglages : erreur {texte_erreur(e)}")
            return {"ok": False, "erreur": texte_erreur(e)}

    # --- rapport pour l'administrateur : PDF sans clé ni nom de client, à joindre à un message ---
    def rapport(self):
        try:
            sortie = Path(self._a.sortie); sortie.mkdir(parents=True, exist_ok=True)
            chemin = sortie / f"rapport-{datetime.now():%Y%m%d-%H%M%S}.pdf"
            ecrire_pdf(chemin, self._rapport_lignes(), f"{TITRE} - rapport pour l'administrateur")
            self._j(f"rapport écrit : {chemin.name}")
            os.startfile(chemin)
            return {"ok": True, "chemin": str(chemin), "dossier": str(sortie)}
        except BaseException as e:
            return {"ok": False, "erreur": texte_erreur(e)}

    def _rapport_lignes(self):
        a, L = self._a, []
        def titre(t): L.extend(["", (t, True)])
        L.append(f"Établi le {datetime.now():%d/%m/%Y à %H:%M}. Sans clé ni nom de client : peut être transmis tel quel.")
        titre("Environnement")
        from importlib.metadata import version as version_paquet
        versions = {}
        for nom in ("pypdf", "pywebview"):
            try:
                versions[nom] = version_paquet(nom)
            except Exception:
                versions[nom] = "absent"
        modes = [m for m, on in (("démo", a.demo), ("lecture seule", a.lecture_seule), ("installation", a.installation)) if on]
        L += [f"Outil : version {VERSION}, dossier {ICI}",
              f"Python {sys.version.split()[0]}, pypdf {versions['pypdf']}, pywebview {versions['pywebview']}, {platform.platform()}",
              "Mode : " + (", ".join(modes) if modes else "normal")]
        titre("Réglages (valeurs secrètes et personnelles masquées)")
        v = {**rg.lire(rg.ODOO_ENV), **rg.lire(rg.MR_ENV)}
        secrets, masques = {"ODOO_API_KEY", "MR_CLE_PRIVEE"}, {"ODOO_USER", "MR_EXPE_TEL", "MR_EXPE_MAIL"}
        for cle in [c[0] for c in rg.CHAMPS_ODOO + rg.CHAMPS_MR]:
            val = v.get(cle, "")
            if cle in secrets:
                L.append(f"{cle} = " + (f"renseignée ({len(val)} caractères)" if val else "(vide)"))
            elif cle in masques:
                L.append(f"{cle} = " + ("renseigné" if val else "(vide)"))
            else:
                L.append(f"{cle} = {val or '(vide)'}")
        if self._c:
            L.append(f"Connexion en cours : base « {self._c['o'].db} », " + ("PRODUCTION, étiquettes payées" if self._c["reel"] else "simulation"))
        titre("Joignabilité au moment du rapport (rien n'est créé)")
        import socket, urllib.error, urllib.request, xmlrpc.client
        delai = socket.getdefaulttimeout(); socket.setdefaulttimeout(6)
        try:
            url = (v.get("ODOO_URL") or "").strip().rstrip("/")
            if url:
                try:
                    info = xmlrpc.client.ServerProxy(f"{mr.resolve_redirect(url)}/xmlrpc/2/common").version()
                    L.append(f"Odoo : répond, version serveur {info.get('server_version', '?')}")
                except Exception as e:
                    L.append(f"Odoo : injoignable ({e})")
            else:
                L.append("Odoo : adresse vide dans les réglages")
            try:
                with urllib.request.urlopen(urllib.request.Request(mr.WS_URL, method="HEAD"), timeout=6) as r:
                    L.append(f"Mondial Relay : répond (HTTP {r.status})")
            except urllib.error.HTTPError as e:
                L.append(f"Mondial Relay : répond (HTTP {e.code})")
            except Exception as e:
                L.append(f"Mondial Relay : injoignable ({e})")
        finally:
            socket.setdefaulttimeout(delai)
        titre("Colis affichés en ce moment")
        L.append(f"{len(self._prets)} à étiqueter : " + ", ".join(f"{b['name']} ({b['origin']})" for b, _, _ in self._prets) if self._prets else "aucun colis à étiqueter")
        for b, why in self._refus:
            L.append(f"refusé {b['name']} ({b['origin'] or '-'}) : {why}")
        titre("Dernières créations (dossier « sortie »)")
        sortie = Path(a.sortie)
        dossiers = sorted((d for d in sortie.iterdir() if d.is_dir() and re.fullmatch(r"\d{8}-\d{4}(\d{2})?", d.name)), reverse=True)[:8] if sortie.is_dir() else []
        if not dossiers:
            L.append("aucune création")
        for d in dossiers:
            L.append((d.name, True))
            for nom, colonnes in (("recap", ("bon", "commande", "poids_g", "n_colis")),
                                  ("refus", ("bon", "commande", "stat", "poids_g", "relais", "pays_relais", "motif", "reponse"))):
                f = d / f"{nom}-{d.name}.csv"
                if f.exists():
                    with open(f, encoding="utf-8-sig", newline="") as fh:
                        for r in csv.DictReader(fh, delimiter=";"):
                            L.append(f"  {nom} : " + "  ".join(f"{c} {r.get(c, '')}" for c in colonnes))
        titre("Journal (dernières lignes)")
        j = Path(a.odoo).parent / "journal.log"
        L += j.read_text(encoding="utf-8").splitlines()[-150:] if j.exists() else ["(pas de journal)"]
        return L


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
