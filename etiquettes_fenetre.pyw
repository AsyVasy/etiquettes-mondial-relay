"""Étiquettes Mondial Relay — la fenêtre principale (même logique que etiquettes_du_jour.py, sans console).

Double-clic sur l'icône « Etiquettes Mondial Relay » du bureau (lancée par pythonw : pas de fenêtre noire).
Usage (administrateur) : pyw -3 etiquettes_fenetre.pyw [--odoo odoo.env] [--mr mondialrelay.env] [--bons WH/OUT/1,WH/OUT/2]
Base de prod → vraies étiquettes payées ; toute autre base → simulation (faux n° TEST).
"""
import argparse, ctypes, os, queue, re, subprocess, sys, threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))  # python -I n'ajoute pas le dossier du script
try:
    import etiquettes_du_jour as mr  # noqa: E402
except ModuleNotFoundError as e:  # pypdf absent : sans ce message, le double-clic ne ferait rien
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror("Étiquettes Mondial Relay",
                         f"Il manque le composant « {e.name} ».\n\nRelancez « Installer (une seule fois).bat »,\n"
                         "ou contactez l'administrateur de l'outil.")
    raise SystemExit(1)
import reglages  # noqa: E402  (fenêtre Réglages : .env et test des connexions)

ROUGE, ORANGE, GRIS, ERREUR = "#c62828", "#e65100", "#555555", "#ffcdd2"
POIDS_MAX = 30  # kg : au-delà, c'est sûrement une faute de frappe (1,25 → 125)


class Fenetre(tk.Tk):
    def __init__(self, a):
        try:  # texte net sur un écran agrandi (125 %, 150 %) au lieu d'une image floue
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        super().__init__()
        self.a, self.c, self.lignes, self.q = a, None, [], queue.Queue()
        self.relais_changes = {}  # bon → n° de relais choisi, gardé quand on actualise
        self.title("Étiquettes Mondial Relay")
        z = self.winfo_fpixels("1i") / 96
        self.geometry(f"{min(int(1000 * z), self.winfo_screenwidth() - 40)}x{min(int(640 * z), self.winfo_screenheight() - 80)}")
        self.minsize(760, 420)
        self.option_add("*Font", ("Segoe UI", 11))

        self.bandeau = tk.Label(self, text="Connexion à Odoo…", font=("Segoe UI", 22, "bold"), fg="white", bg=GRIS, pady=10)
        self.bandeau.pack(fill="x")
        self.sous_titre = tk.Label(self, text="", fg=GRIS)
        self.sous_titre.pack(fill="x")

        tk.Label(self, text="Colis Mondial Relay validés, sans n° de colis — tapez le POIDS PESÉ (emballage compris, ex. 1,25)",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        cadre = tk.Frame(self, bd=1, relief="solid")
        cadre.pack(fill="both", expand=True, padx=12)
        self.toile = tk.Canvas(cadre, highlightthickness=0)
        barre = tk.Scrollbar(cadre, orient="vertical", command=self.toile.yview)
        self.liste = tk.Frame(self.toile)
        self.liste.bind("<Configure>", lambda e: self.toile.configure(scrollregion=self.toile.bbox("all")))
        self.toile.create_window((0, 0), window=self.liste, anchor="nw")
        self.toile.configure(yscrollcommand=barre.set)
        self.toile.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        self.bind_all("<MouseWheel>", lambda e: self.toile.yview_scroll(-e.delta // 120, "units"))

        self.refus = tk.Label(self, text="", fg=ROUGE, justify="left", anchor="w")
        self.refus.pack(fill="x", padx=12, pady=(6, 0))

        bas = tk.Frame(self)
        bas.pack(fill="x", padx=12, pady=10)
        self.etat = tk.Label(bas, text="", fg=GRIS, anchor="w")
        self.etat.pack(side="left", fill="x", expand=True)
        self.b_creer = tk.Button(bas, text="Créer les étiquettes", font=("Segoe UI", 12, "bold"), padx=14, pady=4,
                                 command=self.creer)
        self.b_creer.pack(side="right")
        self.b_actu = tk.Button(bas, text="Actualiser", padx=10, pady=4, command=self.actualiser)
        self.b_actu.pack(side="right", padx=8)
        self.b_regl = tk.Button(bas, text="Réglages…", padx=10, pady=4, command=self.reglages)
        self.b_regl.pack(side="right", padx=8)

        if a.odoo == str(ICI / "odoo.env") and not reglages.complet():
            self.reglages()  # premier lancement : les clés manquent, on les demande d'abord
        else:
            self.travail(lambda: mr.ouvrir(a.odoo, a.mr), self.ouvert, "Connexion à Odoo…")

    # --- travail en arrière-plan : la fenêtre ne gèle pas pendant les appels Odoo / Mondial Relay ---
    def travail(self, fn, suite, message):
        self.b_creer["state"] = self.b_actu["state"] = self.b_regl["state"] = "disabled"
        self.etat["text"] = message + " patientez"
        self.config(cursor="watch")

        def tache():
            try:
                self.q.put((True, fn()))
            except BaseException as e:  # SystemExit des garde-fous compris
                self.q.put((False, e))
        threading.Thread(target=tache, daemon=True).start()
        self.after(150, self.attendre, suite)

    def attendre(self, suite):
        try:
            ok, res = self.q.get_nowait()
        except queue.Empty:
            self.after(150, self.attendre, suite); return
        self.config(cursor="")
        self.etat["text"] = ""
        self.b_actu["state"] = self.b_regl["state"] = "normal"
        self.b_creer["state"] = "normal" if self.c else "disabled"
        if ok:
            suite(res)
        else:
            messagebox.showerror("Étiquettes Mondial Relay", f"{texte_erreur(res)}\n\nSi ça recommence : contactez l'administrateur de l'outil.")

    # --- étapes ---
    def ouvert(self, c):
        self.c = c
        if c["reel"]:
            self.bandeau.config(text="VRAIES ÉTIQUETTES (payées)", bg=ROUGE)
            self.sous_titre["text"] = "Chaque étiquette créée est payée sur le crédit Mondial Relay."
        else:
            self.bandeau.config(text="SIMULATION", bg=ORANGE)
            self.sous_titre["text"] = f"Base Odoo « {c['o'].db} » : rien n'est payé, fausses étiquettes, faux n° TEST."
        self.b_creer["state"] = "normal"
        self.actualiser()

    def reglages(self):
        """Ouvre la fenêtre Réglages (programme à part), puis se reconnecte avec les nouveaux réglages."""
        def apres(_):
            self.c = None
            self.bandeau.config(text="Connexion à Odoo…", bg=GRIS)
            self.sous_titre["text"] = ""
            self.actualiser()
        self.travail(lambda: subprocess.run([sys.executable, str(ICI / "reglages.pyw")]), apres, "Fenêtre Réglages ouverte :")

    def actualiser(self):
        if not self.c:
            self.travail(lambda: mr.ouvrir(self.a.odoo, self.a.mr), self.ouvert, "Connexion à Odoo…"); return
        self.travail(lambda: mr.selection(self.c, self.a.bons, dict(self.relais_changes)), self.afficher,
                     "Lecture des colis dans Odoo…")

    def afficher(self, res):
        prets, refus = res
        saisi = {l["b"]["name"]: (l["poids"].get(), l["pris"].get()) for l in self.lignes}  # gardé si on actualise
        for w in self.liste.winfo_children():
            w.destroy()
        self.lignes = []
        for col, titre in enumerate(["Prendre", "Commande", "Client", "Point relais", "Poids pesé (kg)", ""]):
            tk.Label(self.liste, text=titre, font=("Segoe UI", 10, "bold"), fg=GRIS).grid(row=0, column=col, sticky="w", padx=6, pady=4)
        if not prets:
            tk.Label(self.liste, text="Aucun colis à étiqueter.\nLes bons doivent être VALIDÉS dans Odoo, puis cliquez sur « Actualiser ».",
                     justify="left").grid(row=1, column=0, columnspan=6, sticky="w", padx=6, pady=10)
        for i, (b, p, relais) in enumerate(prets, start=1):
            poids, pris = saisi.get(b["name"], ("", True))
            ligne = {"b": b, "p": p, "relais": relais, "pris": tk.BooleanVar(value=pris)}
            tk.Checkbutton(self.liste, variable=ligne["pris"]).grid(row=i, column=0, padx=6)
            tk.Label(self.liste, text=b["origin"] or b["name"], font=("Segoe UI", 11, "bold")).grid(row=i, column=1, sticky="w", padx=6)
            tk.Label(self.liste, text=p["Dest_Ad1"][:28]).grid(row=i, column=2, sticky="w", padx=6)
            ligne["lab"] = tk.Label(self.liste, text=f"{p['LIV_Rel']} · {relais[:42]}",
                                    fg=ORANGE if b["name"] in self.relais_changes else GRIS)
            ligne["lab"].grid(row=i, column=3, sticky="w", padx=6)
            ligne["poids"] = tk.Entry(self.liste, width=8, justify="right", font=("Segoe UI", 13))
            ligne["poids"].insert(0, poids)
            ligne["poids"].grid(row=i, column=4, padx=6, pady=3)
            ligne["poids"].bind("<Return>", lambda e, n=i: self.suivant(n))
            tk.Button(self.liste, text="Changer de relais", command=lambda l=ligne: self.changer(l)).grid(row=i, column=5, padx=6)
            self.lignes.append(ligne)
        if self.lignes:
            self.lignes[0]["poids"].focus_set()
        self.refus["text"] = ("Pas pris :\n" + "\n".join(f"   {b['origin'] or ''} ({b['name']}) : {why}" for b, why in refus)) if refus else ""
        self.etat["text"] = f"{len(prets)} colis à étiqueter."

    def suivant(self, n):
        if n < len(self.lignes):
            self.lignes[n]["poids"].focus_set()

    def changer(self, ligne):
        b = ligne["b"]
        val = simpledialog.askstring("Changer de point relais",
                                     f"{b['origin']} — {ligne['p']['Dest_Ad1']}\n\nN° du nouveau point relais (6 chiffres) :", parent=self)
        if val is None:
            return
        val = val.strip().upper()
        if not re.fullmatch(r"([A-Z]{2}-)?\d{6}", val):
            messagebox.showerror("Changer de point relais", "Il faut le n° à 6 chiffres du point relais, ex. 036354."); return

        def fait(res):
            ok, info = res
            if not ok:
                messagebox.showerror("Changer de point relais", f"{info}\nLe point relais n'a pas été changé."); return
            ligne["relais"] = info
            self.relais_changes[b["name"]] = val
            ligne["lab"].config(text=f"{ligne['p']['LIV_Rel']} · {info[:42]}", fg=ORANGE)
        self.travail(lambda: mr.changer_relais(self.c, ligne["p"], val), fait, "Vérification du point relais chez Mondial Relay…")

    def creer(self):
        pris = [l for l in self.lignes if l["pris"].get()]
        if not pris:
            messagebox.showinfo("Étiquettes Mondial Relay", "Aucun colis coché."); return
        fautes = []
        for l in pris:
            try:
                l["kg"] = mr.poids_kg(l["poids"].get())
                if l["kg"] > POIDS_MAX:
                    raise ValueError
                l["poids"].config(bg="white")
            except ValueError:
                l["poids"].config(bg=ERREUR); fautes.append(l["b"]["origin"] or l["b"]["name"])
        if fautes:
            messagebox.showerror("Poids pesé", "Poids manquant ou pas compris pour : " + ", ".join(fautes) +
                                 f"\n\nTapez le poids de la balance en kg, ex. 1,25 (maximum {POIDS_MAX} kg).\n"
                                 "Ou décochez le colis s'il ne part pas aujourd'hui."); return
        kg = lambda x: f"{x:.2f}".replace(".", ",")
        recap = "\n".join(f"  {l['b']['origin']}  {l['p']['Dest_Ad1'][:24]}  {kg(l['kg'])} kg" for l in pris)
        reel = self.c["reel"]
        q = (f"Créer {len(pris)} étiquette(s) ?\n\n{recap}\n\n" +
             ("Elles seront PAYÉES sur le crédit Mondial Relay." if reel else "SIMULATION : rien ne sera payé."))
        if not messagebox.askyesno("Confirmer", q, icon="warning" if reel else "question"):
            return
        prets = []
        for l in pris:
            mr.mettre_poids(l["p"], l["kg"])
            prets.append((l["b"], l["p"], l["relais"]))
        self.travail(lambda: mr.creer(self.c, prets, self.a.sortie, dire=lambda *_: None), self.fini,
                     f"Création de {len(prets)} étiquette(s)…")

    def fini(self, res):
        total, faits, echecs = res
        if total:
            os.startfile(total)  # ouvre le PDF pour l'imprimer
        lignes = [f"{f['commande']:<8}  {f['client'][:26]:<26}  n° {f['n_colis']}" for f in faits]
        lignes += [f"{b['origin']:<8}  PAS FAITE : {why}" for b, why in echecs]
        tete = (f"{len(faits)} étiquette(s) créée(s). Le PDF s'est ouvert : imprimez-le.\n"
                "Les n° de colis sont écrits dans Odoo :\n\n") if faits else "Aucune étiquette créée.\n\n"
        f = tk.Toplevel(self)
        f.title("Étiquettes créées")
        t = tk.Text(f, width=64, height=min(18, len(lignes) + 5), font=("Consolas", 11), wrap="none")
        t.insert("1.0", tete + "\n".join(lignes))
        t.config(state="disabled")
        t.pack(padx=12, pady=12)
        tk.Button(f, text="OK", width=10, command=f.destroy).pack(pady=(0, 12))
        f.transient(self)
        self.actualiser()


def texte_erreur(e):
    if isinstance(e, SystemExit):
        return str(e.code)
    if isinstance(e, FileNotFoundError):
        return f"Fichier introuvable : {Path(e.filename).name}"
    if isinstance(e, KeyError):
        return f"Réglage manquant dans un fichier .env : {e}"
    return f"Erreur : {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odoo", default=str(ICI / "odoo.env"))
    ap.add_argument("--mr", default=str(ICI / "mondialrelay.env"))
    ap.add_argument("--bons", default="", help="liste de bons précis, au lieu de la sélection automatique")
    ap.add_argument("--sortie", default=str(ICI / "sortie"))
    Fenetre(ap.parse_args()).mainloop()


if __name__ == "__main__":
    main()
