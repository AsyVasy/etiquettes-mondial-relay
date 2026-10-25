"""Réglages — Étiquettes Mondial Relay.

Ouverte par « Installer (une seule fois).bat » (étape 4) et par le bouton « Réglages… » de la fenêtre principale.
Remplit odoo.env et mondialrelay.env, teste les connexions Odoo et Mondial Relay (gratuit, ne crée rien).
Usage : pyw -3 reglages.pyw [--installation]
"""
import argparse, ctypes, queue, re, sys, threading, xmlrpc.client
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
try:
    import etiquettes_du_jour as mr  # noqa: E402
except ModuleNotFoundError as e:
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror("Réglages", f"Il manque le composant « {e.name} ».\n\nRelancez « Installer (une seule fois).bat »,\n"
                                     "ou contactez l'administrateur de l'outil.")
    raise SystemExit(1)

ODOO_ENV, MR_ENV = ICI / "odoo.env", ICI / "mondialrelay.env"
GRIS, VERT, ROUGE = "#555555", "#2e7d32", "#c62828"

# (clé, libellé, aide, type) — type : "" texte, "secret" masqué, "format" liste, "date"
CHAMPS_ODOO = [
    ("ODOO_URL", "Adresse du site Odoo", "", ""),
    ("ODOO_DB", "Nom de la base", "Base Odoo à laquelle l'outil se connecte.", ""),
    ("ODOO_BASE_PROD", "Base de production", "Nom exact de la base de production : sur elle, les étiquettes sont vraies et payées. "
                                              "Sur toute autre base, ou si ce champ est vide, l'outil reste en simulation.", ""),
    ("ODOO_USER", "Identifiant Odoo", "L'e-mail de connexion à Odoo de la personne qui utilise l'outil.", ""),
    ("ODOO_API_KEY", "Clé API Odoo", "Dans Odoo, avec ce compte : nom en haut à droite > Mon profil > onglet Sécurité du compte > "
                                     "Nouvelle clé API. Choisir la durée la plus longue proposée et noter la date de fin. "
                                     "La clé ne s'affiche qu'une fois : la coller ici tout de suite.", "secret"),
]
CHAMPS_MR = [
    ("MR_ENSEIGNE", "Code enseigne", "Code à 8 caractères du compte Mondial Relay (Offre Start).", ""),
    ("MR_CLE_PRIVEE", "Clé privée", "mondialrelay.fr > Mon profil > Mes paramètres de connexion > Webservices.", "secret"),
    ("MR_EXPE_NOM", "Nom de l'expéditeur", "Imprimé sur l'étiquette.", ""),
    ("MR_EXPE_TEL", "Téléphone de l'expéditeur", "10 chiffres, ex. 0199001234.", ""),
    ("MR_EXPE_MAIL", "E-mail de l'expéditeur", "", ""),
    ("MR_FORMAT", "Format d'impression", "A4 ou A5 = imprimante classique ; 10x15 = imprimante à étiquettes.", "format"),
    ("MR_DEPUIS", "Premier jour d'utilisation", "AAAA-MM-JJ. Les colis validés dans Odoo avant cette date ne sont jamais repris.", "date"),
]
MODELE_ODOO = """# Connexion Odoo. Écrit par la fenêtre Réglages. Ne jamais envoyer ce fichier rempli.
ODOO_URL={ODOO_URL}
ODOO_DB={ODOO_DB}
ODOO_BASE_PROD={ODOO_BASE_PROD}
ODOO_USER={ODOO_USER}
ODOO_API_KEY={ODOO_API_KEY}
"""
MODELE_MR = """# Compte Mondial Relay. Écrit par la fenêtre Réglages. Ne jamais envoyer ce fichier rempli.
MR_ENSEIGNE={MR_ENSEIGNE}
MR_CLE_PRIVEE={MR_CLE_PRIVEE}
MR_MODE_COL={MR_MODE_COL}
MR_FORMAT={MR_FORMAT}
MR_EXPE_NOM={MR_EXPE_NOM}
MR_EXPE_TEL={MR_EXPE_TEL}
MR_EXPE_MAIL={MR_EXPE_MAIL}
MR_DEPUIS={MR_DEPUIS}
"""


def lire(path):
    """Valeurs actuelles : le fichier .env s'il existe, sinon le .exemple, sinon rien."""
    for p in (path, path.with_name(path.name + ".exemple")):
        if p.exists():
            return mr.load_env(p)
    return {}


def complet():
    """Vrai si les deux fichiers existent avec les deux clés remplies (utilisé par la fenêtre principale)."""
    try:
        return bool(mr.load_env(ODOO_ENV).get("ODOO_API_KEY")) and bool(mr.load_env(MR_ENV).get("MR_CLE_PRIVEE"))
    except FileNotFoundError:
        return False


def tester(v):
    """Teste Odoo puis Mondial Relay avec les valeurs saisies. Renvoie [(ok, texte)]. Ne crée et ne paie rien."""
    res, relais = [], None
    db, cle = v["ODOO_DB"], v["ODOO_API_KEY"]
    try:
        url = mr.resolve_redirect(v["ODOO_URL"])
        uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, v["ODOO_USER"], cle, {})
        if not uid:
            raise ValueError("connexion refusée : identifiant, clé API ou nom de base incorrect (ou clé expirée)")
        m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        call = lambda model, meth, *a, **k: m.execute_kw(db, uid, cle, model, meth, list(a), k)
        nom = call("res.users", "read", [uid], fields=["name"])[0]["name"]
        res.append((True, f"Odoo : connecté en tant que {nom}."))
        base_prod = v.get("ODOO_BASE_PROD", "")
        res.append((True, "Odoo : base de PRODUCTION → vraies étiquettes, payées.") if base_prod and db == base_prod
                   else (True, f"Odoo : base « {db} » → SIMULATION, rien n'est payé"
                               + (f" (la base de production déclarée est « {base_prod} »)." if base_prod else " (aucune base de production déclarée).")))
        ecrire = call("stock.picking", "check_access_rights", "write", raise_exception=False)
        res.append((bool(ecrire), "Odoo : droit d'écrire les n° de colis dans les bons : " +
                    ("OK." if ecrire else "MANQUANT (ce compte doit avoir le rôle Inventaire > Utilisateur).")))
        n = call("stock.picking", "search_count", [["carrier_id.is_mondialrelay", "=", True]])
        res.append((True, f"Odoo : {n} bon(s) de livraison Mondial Relay dans la base."))
        rel = call("res.partner", "search_read", [["ref", "=like", "MR#%"]], fields=["ref", "country_id"], limit=1, order="id desc")
        mm = re.fullmatch(r"MR#(\d{6})", rel[0]["ref"]) if rel else None
        if mm:
            pays = call("res.country", "read", [rel[0]["country_id"][0]], fields=["code"])[0]["code"] if rel[0]["country_id"] else "FR"
            relais = (mm.group(1), pays)
        elif rel:
            res.append((False, f"Odoo : le dernier relais enregistré a une référence inattendue ({rel[0]['ref']}) : à signaler à l'administrateur de l'outil."))
    except Exception as e:
        res.append((False, f"Odoo : ÉCHEC — {e}"))
    ens = v["MR_ENSEIGNE"].ljust(8)
    try:
        if relais:
            stat, adr = mr.detail_relais(ens, v["MR_CLE_PRIVEE"], *relais)
            res.append((stat == "0", f"Mondial Relay : OK, relais {relais[0]} reconnu ({adr})." if stat == "0"
                        else f"Mondial Relay : ÉCHEC — STAT {stat} {mr.STAT.get(stat, '')}."))
        else:
            # sans relais connu, on interroge un n° bidon : Mondial Relay contrôle l'enseigne et la clé avant le n° (STAT 1 ou 97
            # si elles sont fausses) ; STAT 14 ou 70 = « n° de relais invalide », donc identifiants acceptés.
            stat, _ = mr.detail_relais(ens, v["MR_CLE_PRIVEE"], "000001", "FR")
            res.append((stat in ("0", "14", "70"), "Mondial Relay : enseigne et clé acceptées (aucun relais dans Odoo pour un test complet)."
                        if stat in ("0", "14", "70") else f"Mondial Relay : ÉCHEC — STAT {stat} {mr.STAT.get(stat, '')}."))
    except Exception as e:
        res.append((False, f"Mondial Relay : ÉCHEC — {e}"))
    return res


def verifier(v):
    """Contrôles avant test ou enregistrement. Renvoie la liste des problèmes."""
    pb = []
    for cle, libelle, _, genre in CHAMPS_ODOO + CHAMPS_MR:
        if not v.get(cle) and cle not in ("MR_EXPE_MAIL", "ODOO_BASE_PROD"):
            pb.append(f"« {libelle} » est vide.")
    if v.get("ODOO_URL") and not v["ODOO_URL"].startswith("https://"):
        pb.append("L'adresse Odoo doit commencer par https://")
    if v.get("MR_EXPE_TEL") and not mr.tel(v["MR_EXPE_TEL"], "FR"):
        pb.append("Téléphone de l'expéditeur : 10 chiffres attendus, ex. 0199001234.")
    if v.get("MR_DEPUIS"):
        try:
            datetime.strptime(v["MR_DEPUIS"], "%Y-%m-%d")
        except ValueError:
            pb.append("Premier jour d'utilisation : format AAAA-MM-JJ attendu, ex. 2026-10-27.")
    return pb


def ecrire(v):
    """Écrit odoo.env et mondialrelay.env (MR_MODE_COL conservé s'il existait déjà)."""
    mode_col = lire(MR_ENV).get("MR_MODE_COL") or "CCC"
    ODOO_ENV.write_text(MODELE_ODOO.format(**v), encoding="utf-8")
    MR_ENV.write_text(MODELE_MR.format(**{**v, "MR_MODE_COL": mode_col}), encoding="utf-8")


class Reglages(tk.Tk):
    def __init__(self, installation):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        super().__init__()
        self.installation, self.q, self.teste_ok = installation, queue.Queue(), False
        self.title("Réglages — Étiquettes Mondial Relay")
        self.option_add("*Font", ("Segoe UI", 11))
        self.resizable(False, False)
        self.champs = {}
        v = {**lire(ODOO_ENV), **lire(MR_ENV)}
        self.mode_col = v.get("MR_MODE_COL") or "CCC"
        if not v.get("MR_DEPUIS"):
            v["MR_DEPUIS"] = date.today().isoformat()

        tk.Label(self, text="Réglages de l'outil Étiquettes Mondial Relay", font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self, text="À remplir une fois. Les clés restent sur ce PC, dans le dossier de l'outil.", fg=GRIS, anchor="w").pack(fill="x", padx=16)
        self.bloc("Odoo", CHAMPS_ODOO, v)
        self.bloc("Mondial Relay", CHAMPS_MR, v)

        self.sortie = tk.Text(self, height=7, width=100, font=("Segoe UI", 10), state="disabled", bg="#f5f5f5", relief="flat", wrap="word")
        self.sortie.pack(fill="x", padx=16, pady=(8, 0))
        self.sortie.tag_config("ok", foreground=VERT)
        self.sortie.tag_config("ko", foreground=ROUGE)
        self.sortie.tag_config("gris", foreground=GRIS)

        bas = tk.Frame(self)
        bas.pack(fill="x", padx=16, pady=12)
        self.b_fermer = tk.Button(bas, text="Fermer sans enregistrer", padx=10, pady=4, command=self.fermer)
        self.b_fermer.pack(side="left")
        self.b_enreg = tk.Button(bas, text="Enregistrer", font=("Segoe UI", 12, "bold"), padx=14, pady=4, command=self.enregistrer)
        self.b_enreg.pack(side="right")
        self.b_test = tk.Button(bas, text="Tester les connexions", padx=10, pady=4, command=self.tester)
        self.b_test.pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.fermer)
        self.dire("Remplissez les champs, cliquez sur « Tester les connexions », puis sur « Enregistrer ».", "gris")

    def bloc(self, titre, champs, v):
        cadre = ttk.LabelFrame(self, text=f" {titre} ")
        cadre.pack(fill="x", padx=16, pady=(10, 0), ipady=4)
        for i, (cle, libelle, aide, genre) in enumerate(champs):
            tk.Label(cadre, text=libelle, anchor="w").grid(row=i, column=0, sticky="nw", padx=(10, 8), pady=4)
            if genre == "format":
                w = ttk.Combobox(cadre, values=["A4", "A5", "10x15"], state="readonly", width=10)
                w.set(v.get(cle) or "A4")
            else:
                w = tk.Entry(cadre, width=44, show="•" if genre == "secret" else "")
                w.insert(0, v.get(cle, ""))
            w.grid(row=i, column=1, sticky="w", pady=4)
            if genre == "secret":
                voir = tk.BooleanVar(value=False)
                tk.Checkbutton(cadre, text="afficher", variable=voir, fg=GRIS,
                               command=lambda w=w, voir=voir: w.config(show="" if voir.get() else "•")).grid(row=i, column=2, sticky="w", padx=4)
            if aide:
                tk.Label(cadre, text=aide, fg=GRIS, font=("Segoe UI", 9), justify="left", wraplength=360, anchor="w").grid(row=i, column=3, sticky="w", padx=(8, 10))
            self.champs[cle] = w

    # --- utilitaires ---
    def valeurs(self):
        return {k: w.get().strip() for k, w in self.champs.items()}

    def dire(self, texte, tag=""):
        self.sortie.config(state="normal")
        self.sortie.delete("1.0", "end")
        self.sortie.insert("end", texte, tag)
        self.sortie.config(state="disabled")

    def verifier(self, v):
        return verifier(v)

    # --- actions ---
    def tester(self):
        v = self.valeurs()
        pb = self.verifier(v)
        if pb:
            self.dire("\n".join(pb), "ko"); return
        self.b_test["state"] = self.b_enreg["state"] = "disabled"
        self.config(cursor="watch")
        self.dire("Test en cours, patientez…", "gris")
        threading.Thread(target=lambda: self.q.put(tester(v)), daemon=True).start()
        self.after(200, self.attendre)

    def attendre(self):
        try:
            res = self.q.get_nowait()
        except queue.Empty:
            self.after(200, self.attendre); return
        self.config(cursor="")
        self.b_test["state"] = self.b_enreg["state"] = "normal"
        self.teste_ok = all(ok for ok, _ in res)
        self.sortie.config(state="normal")
        self.sortie.delete("1.0", "end")
        for ok, texte in res:
            self.sortie.insert("end", ("✔ " if ok else "✘ ") + texte + "\n", "ok" if ok else "ko")
        self.sortie.insert("end", "Tout est bon : cliquez sur « Enregistrer »." if self.teste_ok else
                           "Corrigez ce qui est en rouge, puis testez à nouveau.", "gris")
        self.sortie.config(state="disabled")

    def enregistrer(self):
        v = self.valeurs()
        pb = self.verifier(v)
        if pb:
            self.dire("\n".join(pb), "ko"); return
        if not self.teste_ok and not messagebox.askyesno("Enregistrer", "Les connexions n'ont pas été testées avec succès.\n\nEnregistrer quand même ?",
                                                        icon="warning", parent=self):
            return
        ecrire(v)
        self.teste_ok = False
        if self.installation:
            messagebox.showinfo("Réglages", "Réglages enregistrés : l'installation est terminée.\n\n"
                                            "Icône « Etiquettes Mondial Relay » sur le Bureau.", parent=self)
            self.destroy()
        else:
            messagebox.showinfo("Réglages", "Réglages enregistrés.", parent=self)
            self.destroy()

    def fermer(self):
        if self.installation and not complet():
            if not messagebox.askyesno("Réglages", "Les réglages ne sont pas enregistrés : l'outil ne pourra pas fonctionner.\n\n"
                                                   "Fermer quand même ? (Vous pourrez rouvrir cette fenêtre par le bouton « Réglages… » de l'outil.)",
                                       icon="warning", parent=self):
                return
        self.destroy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installation", action="store_true", help="lancée par l'installateur : messages de fin d'installation")
    Reglages(ap.parse_args().installation).mainloop()


if __name__ == "__main__":
    main()
