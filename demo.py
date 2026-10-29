"""Mode démonstration : Odoo et Mondial Relay remplacés par des données locales, pour s'entraîner sans rien envoyer ni payer.

Lancé par « Etiquettes - mode demo.bat » (etiquettes_app.pyw --demo). Ce fichier ne sert jamais en utilisation réelle :
il remplace seulement, le temps de la démo, les fonctions réseau de etiquettes_du_jour.py et de reglages.pyw.
Tout ce que la démo écrit va dans le sous-dossier « demo » (réglages fictifs, PDF de simulation).
"""
from pathlib import Path

import etiquettes_du_jour as mr
import reglages as rg

ICI = Path(__file__).resolve().parent
DOSSIER = ICI / "demo"

# Points relais connus de la démo : n° → (enseigne, code postal, ville, pays). Tout autre n° est « inconnu » (STAT 14).
RELAIS = {
    "036354": ("TABAC DE LA MAIRIE", "75018", "PARIS", "FR"),
    "012871": ("PRESSING DU CANAL", "59000", "LILLE", "FR"),
    "078210": ("SUPERETTE DES LILAS", "69007", "LYON", "FR"),
    "054433": ("LIBRAIRIE DU PORT", "13002", "MARSEILLE", "FR"),
    "099999": ("RELAIS FERME DEFINITIVEMENT", "33000", "BORDEAUX", "FR"),  # accepté dans la liste, refusé à la création
    "123456": ("NIGHT SHOP CENTRAL", "1000", "BRUXELLES", "BE"),
}
# Bons de livraison fictifs : (n° de bon, commande, client, n° de relais, validé ?)
BONS = [
    ("WH/OUT/00118", "S01234", "MARIE DUPONT", "036354", True),
    ("WH/OUT/00121", "S01240", "JEAN MARTIN", "012871", True),
    ("WH/OUT/00125", "S01251", "SARL DURAND ET FILS", "078210", True),
    ("WH/OUT/00127", "S01255", "CLAIRE BERNARD", "099999", True),  # relais fermé : l'étiquette échouera (STAT 14)
    ("WH/OUT/00130", "S01260", "PAUL LEROY", "054433", False),  # pas encore validé : apparaît après deux « Actualiser »
]
etat = {"bons": [], "actualisations": 0}


class FauxOdoo:
    """Remplace la connexion Odoo : lectures des commandes et frais de port ; tout le reste répond True."""
    db = "demo"

    def __call__(self, model, meth, *a, **k):
        if model == "stock.picking" and meth == "search_read" and a[0] and a[0][0][0] == "carrier_id.is_mondialrelay":  # historique : bons étiquetés
            return [{"id": b["id"], "name": b["name"], "origin": b["origin"], "partner_id": b["partner_id"], "carrier_tracking_ref": b["carrier_tracking_ref"],
                     "date_done": "2026-10-23 08:30:00"} for b in etat["bons"] if b["carrier_tracking_ref"]]
        if model == "res.partner" and meth == "read":
            return [{"id": i, "name": next((b["client"] for b in etat["bons"] if b["id"] == i), ""), "parent_id": False} for i in a[0]]
        if model == "stock.picking" and meth == "search_read":  # commande liée à chaque bon (même n° que le bon, pour la démo)
            ids = a[0][0][2]
            return [{"id": b["id"], "name": b["name"], "sale_id": [b["id"], b["origin"]]} for b in etat["bons"] if b["id"] in ids]
        if model == "sale.order.line" and meth == "search_read":  # frais de port facturés au client : 6,40 € TTC, sauf le 3e colis offert
            ids = a[0][0][2]
            return [{"order_id": [i, ""], "price_subtotal": round(6.40 / 1.2, 2) if i != 3 else 0.0, "price_total": 6.40 if i != 3 else 0.0} for i in ids]
        return True


def _adresse(num):
    nom, cp, ville, _ = RELAIS[num]
    return f"{nom} {cp} {ville}"


def ouvrir(odoo_env, mr_env):
    etat["bons"] = [{"id": i, "name": nom, "origin": cmd, "partner_id": [i, cli], "carrier_tracking_ref": False,
                     "shipping_weight": 0, "weight": 0, "state": "done" if valide else "assigned", "client": cli, "relais": rel}
                    for i, (nom, cmd, cli, rel, valide) in enumerate(BONS, start=1)]
    etat["actualisations"] = 0
    return {"o": FauxOdoo(), "mr": {"MR_FORMAT": "A4"}, "ens": "DEMO    ", "cle": "", "reel": False,
            "expe": {"Expe_Ad1": "MA BOUTIQUE"}}


def detail_relais(ens, cle, num, pays):
    """Gratuit et local : STAT 0 si le relais est connu de la démo, STAT 14 (n° invalide) sinon, et pour le relais fermé."""
    if num in RELAIS and RELAIS[num][3] == pays and num != "099999":
        return "0", _adresse(num)
    return "14", ""


def selection(c, bons="", relais_donnes=None, remplacer=False):
    """Même contrat que etiquettes_du_jour.selection : [(bon, données, relais)] et [(bon, motif)]."""
    etat["actualisations"] += 1
    if etat["actualisations"] == 3:  # au 2e « Actualiser », le bon en attente vient d'être validé dans Odoo
        for b in etat["bons"]:
            b["state"] = "done"
    prets, refus = [], []
    for b in etat["bons"]:
        if b["carrier_tracking_ref"]:
            continue  # a déjà son n° de colis : plus dans la liste, comme dans Odoo
        if b["state"] != "done":
            refus.append((b, "bon pas encore validé")); continue
        p = {"Dest_Ad1": b["client"], "LIV_Rel": b["relais"], "LIV_Rel_Pays": RELAIS[b["relais"]][3], "Poids": "15"}
        relais = _adresse(b["relais"])
        if b["name"] in (relais_donnes or {}):
            ok, info = mr.changer_relais(c, p, relais_donnes[b["name"]])
            if not ok:
                refus.append((b, info)); continue
            relais = info
        prets.append((b, p, relais))
    return prets, refus


def tester(v):
    """Test de connexion fictif : réussit si les deux clés font au moins 4 caractères."""
    res = []
    if len(v.get("ODOO_API_KEY", "")) >= 4:
        res += [(True, "Odoo (démo) : connecté en tant que Utilisateur de démonstration."),
                (True, f"Odoo (démo) : base « {v.get('ODOO_DB', '')} » → SIMULATION, rien n'est payé."),
                (True, "Odoo (démo) : droit d'écrire les n° de colis dans les bons : OK."),
                (True, f"Odoo (démo) : {len(BONS)} bon(s) de livraison Mondial Relay dans la base.")]
    else:
        res.append((False, "Odoo (démo) : ÉCHEC — connexion refusée : identifiant, clé API ou nom de base incorrect (ou clé expirée)"))
    if len(v.get("MR_CLE_PRIVEE", "")) >= 4:
        res.append((True, "Mondial Relay (démo) : OK, relais 036354 reconnu (TABAC DE LA MAIRIE 75018 PARIS)."))
    else:
        res.append((False, "Mondial Relay (démo) : ÉCHEC — STAT 97 clé de sécurité invalide."))
    return res


def suivi(ens, cle, num):
    """Suivi fictif : le colis est en route."""
    return {"ok": True, "stat": "81", "etat": "En cours d'acheminement", "detail": "Prise en charge point relais le 23/10/26 à 15:10, Villeneuve (démo)",
            "relais": "", "evenements": [{"date": "23/10/26", "heure": "08:31", "libelle": "Réception des données", "lieu": ""},
                                         {"date": "23/10/26", "heure": "15:10", "libelle": "Prise en charge point relais", "lieu": "Villeneuve"}]}


def etiquette_pdf(ens, cle, num, fmt="A4"):
    raise RuntimeError("Démo : Mondial Relay n'a pas cette étiquette, seul le PDF de simulation existe.")


_creer = mr.creer


def creer(c, prets, sortie, dire=print):
    """Le vrai creer() (simulation : rien n'est écrit dans Odoo), puis les bons étiquetés reçoivent leur n° fictif
    dans la démo, pour disparaître de la liste comme ils le feraient en production."""
    total, faits, echecs = _creer(c, prets, sortie, dire)
    for f in faits:
        for b in etat["bons"]:
            if b["name"] == f["bon"]:
                b["carrier_tracking_ref"] = f["n_colis"]
    return total, faits, echecs


def activer(a):
    """Branche la démo : fonctions réseau remplacées, réglages et PDF dans le dossier « demo »."""
    DOSSIER.mkdir(exist_ok=True)
    mr.ouvrir, mr.selection, mr.detail_relais, mr.creer = ouvrir, selection, detail_relais, creer  # changer_relais() reste le vrai
    mr.suivi, mr.etiquette_pdf = suivi, etiquette_pdf
    rg.ODOO_ENV, rg.MR_ENV, rg.tester = DOSSIER / "odoo.env", DOSSIER / "mondialrelay.env", tester
    if not rg.ODOO_ENV.exists():
        rg.ecrire({"ODOO_URL": "https://demo.exemple.fr", "ODOO_DB": "demo", "ODOO_BASE_PROD": "", "ODOO_USER": "demo@exemple.fr", "ODOO_API_KEY": "demo-1234",
                   "MR_ENSEIGNE": "DEMO", "MR_CLE_PRIVEE": "demo-1234", "MR_FORMAT": "A4", "MR_EXPE_NOM": "MA BOUTIQUE",
                   "MR_EXPE_TEL": "0199001234", "MR_EXPE_MAIL": "demo@exemple.fr", "MR_DEPUIS": "2026-10-01"})
    a.odoo, a.mr, a.sortie = str(rg.ODOO_ENV), str(rg.MR_ENV), str(DOSSIER / "sortie")
