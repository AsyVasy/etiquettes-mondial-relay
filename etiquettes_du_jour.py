"""Étiquettes Mondial Relay : Odoo → API Mondial Relay → un seul PDF à imprimer → n° de colis écrits dans Odoo.

Version console (administrateur, options --bons --poids --relais --remplacer --verifier).
Pour l'utilisateur : la fenêtre etiquettes_fenetre.pyw, qui réutilise les fonctions de ce fichier.
Bons pris : Mondial Relay, VALIDÉS depuis MR_DEPUIS, SANS n° de suivi. Un bon pas encore validé n'est jamais pris.
- Base Odoo de prod (ODOO_BASE_PROD dans odoo.env) → vraies étiquettes, payées sur le crédit prépayé (après confirmation O/N).
- Toute autre base, ou ODOO_BASE_PROD vide → SIMULATION : aucune étiquette payée, fausse étiquette « SIMULATION », faux n° TEST…,
  et rien n'est écrit dans Odoo.

Usage : python -I -X utf8 etiquettes_du_jour.py [--odoo odoo.env] [--mr mondialrelay.env] [--bons WH/OUT/1,WH/OUT/2] [--oui] [--verifier]
Les clés restent dans les fichiers .env, jamais dans ce script.
"""
import argparse, csv, hashlib, os, random, re, sys, unicodedata, urllib.error, urllib.request, xmlrpc.client
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ICI = Path(__file__).resolve().parent
WS_URL = "https://api.mondialrelay.com/Web_Services.asmx"
NS = "http://www.mondialrelay.fr/webservice/"
MR_SITE = "https://www.mondialrelay.com"
# Ordre exact du WSDL : il sert aussi au calcul de la clé de sécurité.
CHAMPS = ["Enseigne", "ModeCol", "ModeLiv", "NDossier", "NClient", "Expe_Langage", "Expe_Ad1", "Expe_Ad2", "Expe_Ad3",
          "Expe_Ad4", "Expe_Ville", "Expe_CP", "Expe_Pays", "Expe_Tel1", "Expe_Tel2", "Expe_Mail", "Dest_Langage",
          "Dest_Ad1", "Dest_Ad2", "Dest_Ad3", "Dest_Ad4", "Dest_Ville", "Dest_CP", "Dest_Pays", "Dest_Tel1", "Dest_Tel2",
          "Dest_Mail", "Poids", "Longueur", "Taille", "NbColis", "CRT_Valeur", "CRT_Devise", "Exp_Valeur", "Exp_Devise",
          "COL_Rel_Pays", "COL_Rel", "LIV_Rel_Pays", "LIV_Rel", "TAvisage", "TReprise", "Montage", "TRDV", "Assurance",
          "Instructions"]
# Libellés principaux (doc webservice Mondial Relay V5)
STAT = {"0": "OK", "1": "enseigne invalide", "2": "n° d'enseigne vide", "3": "compte enseigne invalide",
        "9": "ville non reconnue", "10": "mode de collecte invalide", "13": "mode de livraison invalide",
        "14": "n° de point relais invalide", "15": "pays du point relais invalide", "20": "poids invalide",
        "27": "mode collecte/livraison invalide", "30": "adresse ligne 1 invalide", "33": "adresse ligne 3 invalide",
        "35": "ville invalide", "36": "code postal invalide", "37": "pays invalide", "38": "téléphone invalide",
        "39": "e-mail invalide", "40": "paramètres manquants", "47": "nombre de colis invalide", "70": "n° de point relais invalide",
        "92": "solde du compte prépayé insuffisant : recharger le crédit", "95": "compte enseigne non activé",
        "96": "type d'enseigne incorrect", "97": "clé de sécurité invalide", "98": "erreur du service", "99": "erreur du service"}


def load_env(path):
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_redirect(url):
    """Suit un éventuel 301/302 sur /xmlrpc/2/common (xmlrpc.client ne le fait pas)."""
    req = urllib.request.Request(f"{url}/xmlrpc/2/common", method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            final = resp.geturl()
    except urllib.error.HTTPError as e:
        final = e.geturl()
    return final.rsplit("/xmlrpc/2/common", 1)[0].rstrip("/")


def txt(s, n, ville=False):
    """Majuscules sans accents, seulement les caractères acceptés par Mondial Relay, coupé à n caractères."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z_\-' ]" if ville else r"[^0-9A-Z_\-'., /]", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:n]


def tel(s, pays):
    d = re.sub(r"\D", "", str(s or ""))
    if not d:
        return ""
    if pays == "FR":
        if d.startswith("33") and len(d) == 11:
            d = "0" + d[2:]
        return d if re.fullmatch(r"0[0-9]{9}", d) else ""
    return "+" + (d[2:] if d.startswith("00") else d.lstrip("0"))


def mail(s):
    s = (s or "").strip()
    return s if re.fullmatch(r"[\w\-.@]{0,70}", s) else ""


def xml_esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Odoo:
    def __init__(self, env_path):
        env = load_env(env_path)
        self.url, self.db, self._k = resolve_redirect(env["ODOO_URL"]), env["ODOO_DB"], env["ODOO_API_KEY"]
        # nom de la base de production : dans odoo.env, sinon dans le odoo.env.exemple voisin (installations d'avant ce réglage)
        exemple = Path(env_path).with_name(Path(env_path).name + ".exemple")
        self.base_prod = env.get("ODOO_BASE_PROD") or (load_env(exemple).get("ODOO_BASE_PROD", "") if exemple.exists() else "")
        self.uid = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common").authenticate(self.db, env["ODOO_USER"], self._k, {})
        if not self.uid:
            raise SystemExit("Odoo : connexion refusée (clé API ?).")
        self._m = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def __call__(self, model, meth, *a, **k):
        return self._m.execute_kw(self.db, self.uid, self._k, model, meth, list(a), k)


def soap(methode, champs, p, cle, extra=""):
    """Appel SOAP Mondial Relay. Clé de sécurité = MD5 en majuscules de toutes les valeurs, dans l'ordre, + clé privée."""
    secu = hashlib.md5(("".join(p[c] for c in champs) + cle).encode("utf-8")).hexdigest().upper()
    corps = "".join(f"<{c}>{xml_esc(p[c])}</{c}>" for c in champs) + f"<Security>{secu}</Security>{extra}"
    env = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
           f'<soap:Body><{methode} xmlns="{NS}">{corps}</{methode}></soap:Body></soap:Envelope>')
    req = urllib.request.Request(WS_URL, data=env.encode("utf-8"), headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}{methode}"'})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = ET.fromstring(r.read()).find(f".//{{{NS}}}{methode}Result")
    return lambda t: (res.findtext(f"{{{NS}}}{t}") or "").strip()


def detail_relais(ens, cle, num, pays):
    """Gratuit, ne crée rien : lit la fiche d'un point relais. STAT 0 = identifiants et relais OK."""
    get = soap("WSI2_DetailPointRelais", ["Enseigne", "Num", "Pays"], {"Enseigne": ens, "Num": num, "Pays": pays}, cle)
    return get("STAT"), " ".join(x for x in (get("LgAdr1"), get("CP"), get("Ville")) if x)


def pdf_simulation(chemin, lignes):
    """Petite page PDF « SIMULATION » (sans bibliothèque) : ce n'est pas une étiquette."""
    lignes = [txt(l, 60) or " " for l in lignes]
    flux = "BT /F1 16 Tf 40 380 Td 22 TL " + " ".join(f"({l.replace('(', ' ').replace(')', ' ')}) '" for l in lignes) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(flux)} >>\nstream\n{flux}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, pos = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        pos.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{p:010d} 00000 n \n" for p in pos)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    Path(chemin).write_bytes(out.encode("latin-1"))


def preparer(o, b, ens, mr, expe):
    """Données Mondial Relay d'un bon, ou (None, motif du refus)."""
    rel = o("res.partner", "read", [b["partner_id"][0]], fields=["ref", "zip", "city", "street", "street2", "country_id",
                                                                 "parent_id", "is_mondialrelay", "name"])[0]
    m = re.fullmatch(r"MR#(\d{6})", rel["ref"] or "")
    if not rel["is_mondialrelay"] or not m:
        return None, "pas de point relais Mondial Relay"
    poids_kg = b["shipping_weight"] or b["weight"] or 0  # remplacé ensuite par le poids pesé
    cli = o("res.partner", "read", [rel["parent_id"][0]], fields=["name", "phone", "mobile", "email", "street", "street2",
                                                                   "zip", "city", "country_id"])[0] if rel["parent_id"] else {}
    pays_rel = o("res.country", "read", [rel["country_id"][0]], fields=["code"])[0]["code"]
    # Adresse du destinataire : la sienne si elle est complète, sinon celle du point relais.
    adr = cli if cli.get("street") and cli.get("zip") and cli.get("city") else rel
    pays_dest = o("res.country", "read", [adr["country_id"][0]], fields=["code"])[0]["code"] if adr.get("country_id") else pays_rel
    p = {"Enseigne": ens, "ModeCol": mr.get("MR_MODE_COL", "CCC"), "ModeLiv": "24R",
         "NDossier": re.sub(r"[^0-9A-Z_ -]", "", txt(b["origin"], 15)), "NClient": "", **expe,
         "Dest_Langage": "FR", "Dest_Ad1": txt(cli.get("name") or rel["name"], 32), "Dest_Ad2": "",
         "Dest_Ad3": txt(adr["street"], 32), "Dest_Ad4": txt(adr.get("street2"), 32),
         "Dest_Ville": txt(adr["city"], 26, True), "Dest_CP": (adr["zip"] or "").replace(" ", ""), "Dest_Pays": pays_dest,
         "Dest_Tel1": tel(cli.get("mobile") or cli.get("phone"), pays_dest), "Dest_Tel2": "", "Dest_Mail": mail(cli.get("email")),
         "Poids": str(max(int(round(poids_kg * 1000)), 15)), "Longueur": "", "Taille": "", "NbColis": "1",
         "CRT_Valeur": "0", "CRT_Devise": "", "Exp_Valeur": "", "Exp_Devise": "",
         "COL_Rel_Pays": "", "COL_Rel": "", "LIV_Rel_Pays": pays_rel, "LIV_Rel": m.group(1),
         "TAvisage": "", "TReprise": "", "Montage": "", "TRDV": "", "Assurance": "", "Instructions": ""}
    return p, rel["name"]


def ouvrir(odoo_env, mr_env):
    """Connexion Odoo + identifiants Mondial Relay + garde-fous. Contexte partagé par la console et la fenêtre."""
    mr = load_env(mr_env)
    ens, cle = mr["MR_ENSEIGNE"].ljust(8), mr["MR_CLE_PRIVEE"]
    o = Odoo(odoo_env)
    reel = bool(o.base_prod) and o.db == o.base_prod
    if reel and ens.startswith("BDTEST"):
        raise SystemExit("Refus : enseigne de test sur la base de prod.")
    soc = o("res.company", "read", [1], fields=["name", "street", "street2", "zip", "city", "email"])[0]
    expe = {"Expe_Langage": "FR", "Expe_Ad1": txt(mr.get("MR_EXPE_NOM", soc["name"]), 32), "Expe_Ad2": "",
            "Expe_Ad3": txt(soc["street"], 32), "Expe_Ad4": txt(soc["street2"], 32), "Expe_Ville": txt(soc["city"], 26, True),
            "Expe_CP": soc["zip"], "Expe_Pays": "FR", "Expe_Tel1": tel(mr.get("MR_EXPE_TEL"), "FR"), "Expe_Tel2": "",
            "Expe_Mail": mail(mr.get("MR_EXPE_MAIL", soc["email"]))}
    if not expe["Expe_Tel1"]:
        raise SystemExit("MR_EXPE_TEL manquant ou invalide dans le fichier mondialrelay.env.")
    return {"o": o, "mr": mr, "ens": ens, "cle": cle, "reel": reel, "expe": expe}


def changer_relais(c, p, valeur):
    """Change le point relais d'un colis (ex. 036354 ou BE-123456), vérifié chez Mondial Relay (gratuit).
    Renvoie (True, adresse du relais) ou (False, motif)."""
    pays, _, num = valeur.strip().upper().rpartition("-")
    stat, adr = detail_relais(c["ens"], c["cle"], num, pays or "FR")
    if stat != "0":
        return False, f"nouveau relais {num} inconnu chez Mondial Relay (STAT {stat})"
    p.update(LIV_Rel=num, LIV_Rel_Pays=pays or "FR")
    return True, f"{adr} (changé)"


def selection(c, bons="", relais_donnes=None, remplacer=False):
    """Bons à étiqueter [(bon, données MR, relais)] et bons refusés [(bon, motif)]."""
    o, mr, relais_donnes = c["o"], c["mr"], relais_donnes or {}
    depuis = mr.get("MR_DEPUIS") or datetime.now().strftime("%Y-%m-%d")
    # minuit à Paris ≈ 22:00 UTC la veille (marge de 2 h)
    depuis_utc = (datetime.strptime(depuis, "%Y-%m-%d") - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    if bons:
        dom = [["name", "in", [x.strip() for x in bons.split(",")]]]
    else:
        dom = [["carrier_id.is_mondialrelay", "=", True], ["state", "=", "done"], ["carrier_tracking_ref", "=", False],
               ["date_done", ">=", depuis_utc]]
    liste = o("stock.picking", "search_read", dom, fields=["name", "origin", "partner_id", "carrier_tracking_ref",
                                                          "shipping_weight", "weight", "state"], order="date_done, id")
    prets, refus = [], []
    for b in liste:
        if b["carrier_tracking_ref"] and not (remplacer and bons):
            refus.append((b, f"a déjà un n° de suivi ({b['carrier_tracking_ref']})")); continue
        if b["state"] != "done":
            refus.append((b, "bon pas encore validé")); continue
        p, info = preparer(o, b, c["ens"], mr, c["expe"])
        if p and b["name"] in relais_donnes:
            ok, info = changer_relais(c, p, relais_donnes[b["name"]])
            if not ok:
                refus.append((b, info)); continue
        (prets.append((b, p, info)) if p else refus.append((b, info)))
    return prets, refus


def poids_kg(val):
    """Poids tapé (virgule acceptée) → kg. ValueError si vide, illisible ou ≤ 0."""
    kg = float((val or "").strip().replace(",", "."))
    if kg <= 0:
        raise ValueError
    return kg


def mettre_poids(p, kg):
    p["Poids"] = str(max(int(round(kg * 1000)), 15))


def creer(c, prets, sortie, dire=print):
    """Crée les étiquettes (vraies en prod, simulation ailleurs), assemble un PDF unique + un récap CSV.
    En prod, le n° de colis est écrit dans le bon (carrier_tracking_ref, rien d'autre) dès la réponse de Mondial Relay,
    avant le téléchargement du PDF : une étiquette payée est toujours enregistrée. En simulation, Odoo n'est pas modifié.
    Chaque refus garde ce qui a été envoyé (poids, relais, adresse, jamais la clé) dans refus-<horodatage>.csv.
    Renvoie (chemin du PDF ou None, faits, échecs)."""
    o, mr, reel = c["o"], c["mr"], c["reel"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # à la seconde : deux créations dans la même minute ne s'écrasent plus
    out = Path(sortie) / stamp
    out.mkdir(parents=True, exist_ok=True)
    fmt = mr.get("MR_FORMAT", "A4")
    pdf, faits, refus = PdfWriter(), [], []  # refus : (bon, données envoyées, STAT, motif)
    def echec(b, p, stat, why):
        refus.append((b, p, stat, why)); dire(f"  ÉCHEC  {b['origin']} : {why}")
    for b, p, relais in prets:
        fichier = out / f"{b['name'].replace('/', '-')}.pdf"
        if reel:
            get = soap("WSI2_CreationEtiquette", CHAMPS, p, c["cle"], "<Texte></Texte>")
            stat, num, url = get("STAT"), get("ExpeditionNum"), get("URL_Etiquette")
            if stat != "0":
                echec(b, p, stat, f"Mondial Relay STAT {stat} {STAT.get(stat, 'voir la doc')} (poids envoyé {p['Poids']} g)"); continue
            try:  # tout de suite : l'étiquette est payée, le bon ne doit plus jamais être reproposé
                o("stock.picking", "write", [b["id"]], {"carrier_tracking_ref": num})
            except Exception as e:
                raise RuntimeError(f"Étiquette {num} créée pour le bon {b['name']}, mais n° NON écrit dans Odoo ({e}). "
                                   f"Notez ce n° dans le bon avant de relancer, sinon une 2e étiquette serait payée.") from e
            try:
                with urllib.request.urlopen(MR_SITE + re.sub(r"format=[^&]*", f"format={fmt}", url), timeout=60) as r:
                    fichier.write_bytes(r.read())
            except Exception as e:
                echec(b, p, "0", f"étiquette {num} créée et n° écrit dans le bon, mais PDF non téléchargé ({e}) : "
                                 f"à réimprimer depuis l'espace Mondial Relay"); continue
        else:
            stat, adr = detail_relais(c["ens"], c["cle"], p["LIV_Rel"], p["LIV_Rel_Pays"])
            if stat != "0":
                echec(b, p, stat, f"Mondial Relay STAT {stat} {STAT.get(stat, '')}"); continue
            num = f"TEST{random.randint(0, 9999):04d}"
            pdf_simulation(fichier, ["SIMULATION - PAS UNE ETIQUETTE", "", f"Commande {b['origin']}  Bon {b['name']}",
                                     p["Dest_Ad1"], f"Relais {p['LIV_Rel']} : {adr}", f"Poids {p['Poids']} g",
                                     f"N de colis fictif {num}"])
        for page in PdfReader(str(fichier)).pages:
            pdf.add_page(page)
        faits.append({"commande": b["origin"], "bon": b["name"], "client": p["Dest_Ad1"], "relais": relais,
                      "poids_g": p["Poids"], "n_colis": num})
        dire(f"  OK     {b['origin']} → n° de colis {num} " + (f"écrit dans le bon {b['name']}" if reel else "(fictif, rien n'est écrit dans Odoo)"))
    if refus:  # trace des refus (sans clé) : ce qui a été envoyé, pour comprendre un STAT sans deviner
        with open(out / f"refus-{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["commande", "bon", "stat", "poids_g", "relais", "pays_relais", "cp", "pays", "motif"])
            w.writerows([b["origin"], b["name"], stat, p.get("Poids"), p.get("LIV_Rel"), p.get("LIV_Rel_Pays"), p.get("Dest_CP"), p.get("Dest_Pays"), why]
                        for b, p, stat, why in refus)
    echecs = [(b, why) for b, _, _, why in refus]
    if not faits:
        return None, faits, echecs
    total = out / f"etiquettes-{stamp}.pdf"
    with open(total, "wb") as f:
        pdf.write(f)
    with open(out / f"recap-{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(faits[0]), delimiter=";"); w.writeheader(); w.writerows(faits)
    return total, faits, echecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odoo", default=str(ICI / "odoo.env"))
    ap.add_argument("--mr", default=str(ICI / "mondialrelay.env"))
    ap.add_argument("--bons", default="", help="liste de bons précis, au lieu de la sélection automatique")
    ap.add_argument("--oui", action="store_true", help="ne pas demander de confirmation")
    ap.add_argument("--verifier", action="store_true", help="contrôle gratuit des relais, ne crée rien")
    ap.add_argument("--poids", default="", help="poids pesés, ex. WH/OUT/1=1.2,WH/OUT/2=0.8 (sinon demandés à l'écran)")
    ap.add_argument("--relais", default="", help="changer de point relais, ex. WH/OUT/1=036354 ou WH/OUT/1=BE-123456")
    ap.add_argument("--remplacer", action="store_true", help="refaire l'étiquette d'un bon de --bons qui a déjà un n°")
    ap.add_argument("--sortie", default=str(ICI / "sortie"))
    a = ap.parse_args()

    c = ouvrir(a.odoo, a.mr)
    reel = c["reel"]
    print("=" * 70)
    print(f"  ÉTIQUETTES MONDIAL RELAY — base Odoo « {c['o'].db} »")
    print("  " + ("VRAIES ÉTIQUETTES, payées sur le crédit prépayé" if reel else "SIMULATION : aucune étiquette payée, faux n° TEST, rien n'est écrit dans Odoo"))
    print("=" * 70)

    # Séparateur entre bons : virgule ou point-virgule suivi d'un nom de bon (la virgule décimale reste possible).
    liste = lambda s: dict(x.strip().split("=", 1) for x in re.split(r"[,;]\s*(?=[A-Z]+/)", s) if "=" in x)
    poids_donnes, relais_donnes = liste(a.poids), liste(a.relais)
    prets, refus = selection(c, a.bons, relais_donnes, a.remplacer)

    print(f"\nBons Mondial Relay validés, sans n° de suivi : {len(prets)}\n")
    for b, p, relais in prets:
        print(f"  {b['origin']:<8} {p['Dest_Ad1'][:24]:<24} relais {relais[:40]}")
    for b, why in refus:
        print(f"  REFUSÉ  {b['origin']:<8} {b['name']} : {why}")
    if not prets:
        print("\nRien à faire. (Les bons doivent être VALIDÉS dans Odoo avant de lancer l'outil.)")
        return
    if a.verifier:
        for b, p, _ in prets:
            stat, adr = detail_relais(c["ens"], c["cle"], p["LIV_Rel"], p["LIV_Rel_Pays"])
            print(f"  vérif {b['origin']} relais {p['LIV_Rel']} : STAT {stat} {STAT.get(stat, '')} {adr}")
        return
    # Poids pesé, emballage compris : celui d'Odoo vient des fiches produits et est souvent trop bas.
    print("\nPoids PESÉ de chaque colis, emballage compris (en kg, ex. 1,25) :")
    for b, p, _ in list(prets):
        val = poids_donnes.get(b["name"])
        while val is None and not a.oui:
            val = input(f"  {b['origin']} {p['Dest_Ad1'][:24]} : ").strip() or None
            try:
                if val:
                    poids_kg(val)
            except ValueError:
                print("    poids non compris, recommencez (ex. 1,25)"); val = None
        if val is None:
            prets.remove((b, p, _)); print(f"  REFUSÉ  {b['origin']} : poids pesé non donné"); continue
        kg = poids_kg(val)
        mettre_poids(p, kg)
        print(f"  {b['origin']} : {kg:.2f} kg")
    if not prets:
        return
    q = f"\nCréer {len(prets)} étiquette(s) {'(PAYÉES sur le crédit)' if reel else '(simulation)'} ? Tapez O puis Entrée : "
    if not a.oui and input(q).strip().upper() != "O":
        print("Annulé, rien n'a été fait."); return

    total, faits, _ = creer(c, prets, a.sortie)
    if total:
        print(f"\n{len(faits)} étiquette(s) prête(s) : {total}")
        if not a.oui:
            os.startfile(total)  # ouvre le PDF pour l'imprimer


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"\n{e.code}")
    except Exception as e:  # message lisible plutôt qu'une trace
        print(f"\nErreur : {e}")
