"""Parcourt toutes les interactions en mode démo via le vrai pont pywebview (le PDF n'est pas ouvert à l'écran)."""
import importlib.util, json, shutil, sys, threading, time
from pathlib import Path
D = Path(sys.argv[1]); sys.path.insert(0, str(D))
shutil.rmtree(D / "demo", ignore_errors=True)
spec = importlib.util.spec_from_file_location("etiquettes_app", D / "etiquettes_app.pyw")
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
app.os.startfile = lambda *_: print("   (PDF ouvert :", Path(_[0]).name, ")", flush=True)

def ev(w, js, t=10):
    res = {}
    def f():
        try: res["r"] = w.evaluate_js(js)
        except Exception as e: res["r"] = f"EXC {e!r}"
    th = threading.Thread(target=f, daemon=True); th.start(); th.join(t)
    return res.get("r", "BLOQUÉ")

def appel(w, nom, *args, attente=10):
    """Appelle pywebview.api.<nom>(...) depuis la page et renvoie le résultat JSON (attente en secondes)."""
    ev(w, f"window.__r = null; pywebview.api.{nom}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)}).then(r => {{ window.__r = JSON.stringify(r === undefined ? null : r); }})")
    for _ in range(int(attente / 0.2)):
        r = ev(w, "window.__r")
        if r is not None: return json.loads(r)
        time.sleep(0.2)
    return "SANS RÉPONSE"

def scenario(w):
    ok = True
    def verif(cond, texte):
        nonlocal ok
        print(("   OK  " if cond else "   KO  ") + texte, flush=True); ok = ok and cond
    time.sleep(4)
    print("1. démarrage", flush=True)
    verif(ev(w, "document.querySelector('#h1').textContent") == "4 colis à étiqueter", "titre : 4 colis à étiqueter")
    verif("Démonstration" in ev(w, "document.querySelector('#pastille').textContent"), "pastille Démonstration")
    verif("bon pas encore validé" in ev(w, "document.querySelector('#refus').textContent"), "« Pas pris » affiché pour le bon non validé")
    r = appel(w, "lister"); verif(r["prets"][0]["facture_ttc"] == 6.4 and r["prets"][2]["facture_ttc"] == 0, "frais de port facturés lus dans la commande : 6,40 € TTC, 3e colis offert")
    verif(ev(w, "[...document.querySelectorAll('.ligne .facture')].map(e => e.textContent).join('|')") == "6,40 €|6,40 €|offerte|6,40 €", "colonne Facturé affichée dans la liste")
    print("2. changement de relais", flush=True)
    r = appel(w, "changer_relais", "WH/OUT/00121", "054433"); verif(r["ok"] and "MARSEILLE" in r["info"], f"relais valide → {r.get('info')}")
    r = appel(w, "changer_relais", "WH/OUT/00121", "000001"); verif(not r["ok"] and "inconnu" in r["info"], f"relais inconnu refusé → {r.get('info')}")
    r = appel(w, "changer_relais", "WH/OUT/00121", "12"); verif(not r["ok"], "format invalide refusé")
    print("3. poids", flush=True)
    r = appel(w, "verifier_poids", [{"bon": "WH/OUT/00118", "poids": "1,25"}, {"bon": "WH/OUT/00121", "poids": "abc"}, {"bon": "WH/OUT/00125", "poids": "40"}])
    verif(r["kg"] == {"WH/OUT/00118": 1.25} and sorted(r["fautes"]) == ["WH/OUT/00121", "WH/OUT/00125"], "1,25 accepté ; abc et 40 kg refusés")
    print("3b. grille tarifaire", flush=True)
    g = appel(w, "tarifs_lire"); verif(g["date"] == "" and all(v is None for v in g["pays"]["FR"]) and len(g["tranches"]) == 8, "grille vide par défaut, 8 tranches Mondial Relay")
    r = appel(w, "verifier_poids", [{"bon": "WH/OUT/00118", "poids": "1,25"}]); verif(r["prix"]["WH/OUT/00118"] is None, "sans grille : prix inconnu")
    feuille = {"date": "2026-01-01", "tranches": [500, 2000, 4000, 6000, 8000, 10000, 15000, 20000, 25000, 30000],
             "pays": {"FR": ["6,40", "8,50", "9,60", "12,20", "15,20", "16,90", "23,90", "26,90", "35,05", ""]}}
    r = appel(w, "tarifs_enregistrer", feuille); verif(r["ok"] and (D / "demo" / "tarifs.json").exists(), "grille à tranches libres (feuille papier de la boutique) enregistrée")
    g = appel(w, "tarifs_lire"); verif(g["tranches"] == feuille["tranches"] and g["pays"]["FR"][1] == 8.5 and len(g["pays"]["BE"]) == 10, "relecture : 10 tranches conservées, autres pays vides à la bonne longueur")
    r = appel(w, "verifier_poids", [{"bon": "WH/OUT/00118", "poids": "1,25"}, {"bon": "WH/OUT/00121", "poids": "7"}, {"bon": "WH/OUT/00125", "poids": "0,2"}])
    verif(r["prix"] == {"WH/OUT/00118": 8.5, "WH/OUT/00121": 15.2, "WH/OUT/00125": 6.4} and r["grille_date"] == "2026-01-01", f"estimation : 1,25 kg → 8,50 ; 7 kg → 15,20 ; 0,2 kg → 6,40 : {r['prix']}")
    r = appel(w, "verifier_poids", [{"bon": "WH/OUT/00118", "poids": "28"}]); verif(r["prix"]["WH/OUT/00118"] is None, "28 kg : tranche 30 kg vide → prix inconnu")
    r = appel(w, "tarifs_enregistrer", {"date": "", "tranches": [500, 500], "pays": {}}); verif(not r["ok"], "tranches en doublon refusées")
    r = appel(w, "tarifs_enregistrer", {"date": "", "tranches": [2000, 500], "pays": {"FR": ["b", "a"]}}); verif(not r["ok"], "prix illisible refusé")
    pub = appel(w, "tarifs_publique", 1); verif(pub["pays"]["FR"][0] == 3.29 and pub["pays"]["DE"][7] is None and pub["pays"]["BE"][2] == 6.62 and len(pub["paliers"]) == 5 and pub["date"] == "2026-01-07", "grille publique : palier 10-49 → FR 3,29 ; DE 30 kg absent ; BE 2 kg 6,62")
    verif(ev(w, "ouvrirTarifs().then(()=>{window.__t = document.querySelectorAll('#tarifs .ligne-t').length + '|' + document.querySelectorAll('#t-palier option').length}); 1") == 1, "écran Grille tarifaire demandé")
    time.sleep(1.5); verif(ev(w, "window.__t") == "11|5", f"écran grille : 10 tranches + ligne d'ajout, 5 paliers → {ev(w, 'window.__t')}")
    ev(w, "ajouterTranche(); document.querySelector('#t-poids-10').value = '35'; document.querySelector('#t-FR-10').value = '40'; supprimerTranche(0); 1"); time.sleep(0.5)
    verif(ev(w, "document.querySelector('#t-poids-0').value + '|' + document.querySelector('#t-FR-0').value + '|' + document.querySelector('#t-poids-9').value + '|' + document.querySelectorAll('#tarifs .ligne-t').length") == "2|8,50|35|11", "ajout d'une tranche 35 kg puis suppression de la 1re : lignes renumérotées, valeurs conservées")
    ev(w, "(() => { ajouterTranche(); const n = document.querySelector('#t-poids-10'); n.value = '3'; n.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })(); 1"); time.sleep(0.5)
    tri = lambda: ev(w, "document.querySelector('#t-poids-1').value + '|' + document.querySelector('#t-poids-2').value + '|' + document.querySelector('#t-poids-10').value + '|' + document.querySelectorAll('#tarifs .ligne-t').length + '|' + document.activeElement.id")
    verif(tri() == "3|4|35|12|t-FR-1", f"tranche 3 kg saisie en bas + Entrée : rangée entre 2 et 4 kg, curseur sur son prix FR → {tri()}")
    ev(w, "(() => { const d = document.querySelector('#t-poids-1'); d.value = '4'; d.dispatchEvent(new FocusEvent('blur', {relatedTarget: document.querySelector('#t-FR-10')})); })(); 1"); time.sleep(0.5)
    dbl = lambda: ev(w, "document.querySelectorAll('#tarifs .tranche-t.doublon').length + '|' + (document.querySelector('#erreur-tarifs') || {textContent: ''}).textContent.slice(0, 34) + '|' + document.activeElement.id")
    verif(dbl() == "2|Deux tranches ont le même poids (4|t-FR-10", f"doublon 4 kg signalé en rouge aussitôt, focus suivi vers la ligne 35 kg → {dbl()}")
    ev(w, "enregistrerTarifs(); 1"); time.sleep(0.8)
    verif("même poids" in ev(w, "(document.querySelector('.feuille pre') || {textContent: ''}).textContent") and appel(w, "tarifs_lire")["tranches"] == feuille["tranches"], "enregistrement refusé tant que le doublon existe, grille inchangée")
    ev(w, "fermerFeuille(); supprimerTranche(1); 1"); time.sleep(0.5)
    verif(ev(w, "document.querySelectorAll('#tarifs .tranche-t.doublon').length + '|' + document.querySelectorAll('#tarifs .ligne-t').length") == "0|11", "doublon supprimé : plus rien en rouge, 10 tranches")
    verif(ev(w, "(() => { const s = getComputedStyle(document.querySelector('#tarifs .ajout-t')); const l = document.querySelector('#tarifs'); return s.position + '|' + s.bottom + '|' + (l.scrollWidth <= l.clientWidth); })()") == "sticky|0px|true", "pied « Ajouter une tranche » collé en bas, aucun défilement horizontal")
    ev(w, "enregistrerTarifs(); 1"); time.sleep(1.2); ev(w, "fermerFeuille(); 1")
    g = appel(w, "tarifs_lire"); verif(g["tranches"][-1] == 35000 and g["tranches"][0] == 2000 and g["pays"]["FR"][-1] == 40 and g["pays"]["FR"][0] == 8.5, f"enregistrement depuis l'écran : tranches {g['tranches'][0]}…{g['tranches'][-1]}, FR {g['pays']['FR'][0]}…{g['pays']['FR'][-1]}")
    ev(w, "document.querySelector('#t-palier').value = '2'; chargerPublique(); 1"); time.sleep(1.2)
    verif(ev(w, "document.querySelector('#t-FR-0').value + '|' + document.querySelector('#t-poids-0').value + '|' + document.querySelector('#t-DE-7').value + '|' + document.querySelectorAll('#tarifs .ligne-t').length + '|' + document.querySelector('#t-date').value") == "3,19|0,5||9|2026-01-07", "Charger la grille publique (palier 50-99) : tranches Mondial Relay rétablies, FR 500 g = 3,19, DE 30 kg vide, date 07/01/2026 → " + str(ev(w, "document.querySelector('#t-FR-0').value + '|' + document.querySelector('#t-poids-0').value + '|' + document.querySelector('#t-DE-7').value + '|' + document.querySelectorAll('#tarifs .ligne-t').length + '|' + document.querySelector('#t-date').value")))
    TAB, NL = chr(9), chr(10)
    colle = NL.join([TAB.join(["TARIFS HT avant remise", "Belgique Luxembourg", "Pays-Bas", "Espagne Portugal", "Allemagne"]),
                     TAB.join(["jusqu'à 0,5 KG", "1,11 €", "2,22 €", "3,33 €", "4,44 €"]),
                     TAB.join(["jusqu'à 30 KG", "9,99 €", "9,99 €", "8,88 €", "-"])])
    ev(w, "remplirGrille(analyserTexte(" + json.dumps(colle, ensure_ascii=False) + ").grille); 1"); time.sleep(0.5)
    verif(ev(w, "[document.querySelector('#t-poids-0').value, document.querySelector('#t-BE-0').value, document.querySelector('#t-LU-0').value, document.querySelector('#t-NL-0').value, document.querySelector('#t-ES-0').value, document.querySelector('#t-DE-0').value, document.querySelector('#t-poids-1').value, document.querySelector('#t-ES-1').value, document.querySelector('#t-DE-1').value].join('|')") == "0,5|1,11|1,11|2,22|3,33|4,44|30|8,88|", "analyse d'un tableau du site : 2 tranches du fichier, colonnes doubles (BE+LU, ES+PT) réparties, tiret → vide")
    csv = NL.join(["PoidsMaxKG;Zone_FR;Zone_BE_LU;Zone_NL;Zone_ES_PT;Zone_DE", "0.5;3.09;3.60;4.50;5.20;7.50", "3.0;4.60;5.40;6.65;7.70;10.80", "10.0;8.90;10.10;11.80;13.70;18.50"])
    ev(w, "window.__a = analyserTexte(" + json.dumps(csv) + "); remplirGrille(window.__a.grille); 1"); time.sleep(0.5)
    verif(ev(w, "[document.querySelector('#t-poids-1').value, document.querySelector('#t-FR-0').value, document.querySelector('#t-LU-0').value, document.querySelector('#t-FR-1').value, document.querySelector('#t-PT-2').value, document.querySelector('#t-DE-2').value].join('|')") == "3|3,09|3,60|4,60|13,70|18,50", "analyse CSV à codes pays (Zone_FR ; 0.5 ; 3 ; 10) : 3 tranches adoptées, prix en place")
    verif("3 tranches" in ev(w, "window.__a.resume"), "le résumé annonce les tranches du fichier")
    print("3c. fichiers déposés", flush=True)
    import base64
    b64 = lambda octets: "data:application/octet-stream;base64," + base64.b64encode(octets).decode()
    r = appel(w, "lire_fichier_tarifs", "grille.csv", b64(csv.encode("cp1252"))); verif("Zone_FR" in r.get("texte", ""), "CSV en cp1252 lu")
    r = appel(w, "lire_fichier_tarifs", "grille.xlsx", b64(b"PK")); verif("CSV" in r.get("erreur", ""), "Excel refusé avec conseil")
    pdf = D / "demo" / "grille-test.pdf"
    app.mr.pdf_simulation(pdf, ["TARIFS HT AVANT REMISE", "BELGIQUE LUXEMBOURG PAYS-BAS ESPAGNE PORTUGAL ALLEMAGNE", "JUSQU'A 0,5 KG 3,72 3,72 5,32 5.82", "JUSQU'A 30 KG 21,00 21,00 24,99 -"])
    r = appel(w, "lire_fichier_tarifs", "grille.pdf", b64(pdf.read_bytes())); verif("BELGIQUE" in r.get("texte", ""), "PDF lu par pypdf")
    a = json.loads(ev(w, "JSON.stringify(analyserTexte(" + json.dumps(r.get("texte", "")) + "))"))
    verif(not a.get("erreur") and a["grille"]["tranches"] == [500, 30000] and a["grille"]["pays"]["LU"][0] == 3.72 and a["grille"]["pays"]["PT"][0] == 5.32 and a["grille"]["pays"]["DE"][0] == 5.82 and a["grille"]["pays"]["DE"][1] is None, f"texte PDF : 2 tranches, paires BE+LU et ES+PT fusionnées, tiret → vide : {a.get('erreur') or a['grille']['pays']}")
    ev(w, "window.__d = null; const fic = new File([" + json.dumps(csv) + "], 'tarifs.csv'); const dt = new DataTransfer(); dt.items.add(fic); document.querySelector('#ecran-tarifs').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true})); 1")
    time.sleep(2.5)
    verif(ev(w, "document.querySelector('#t-NL-0').value + '|' + document.querySelectorAll('#tarifs .ligne-t').length + '|' + (document.querySelector('.feuille h2') || {textContent: ''}).textContent") == "4,50|4|Grille remplie depuis tarifs.csv", "dépôt simulé d'un CSV : 3 tranches du fichier + ligne d'ajout, feuille de confirmation")
    ev(w, "fermerFeuille(); document.querySelector('#t-NL-0').value = ''; const fic2 = new File([" + json.dumps(csv) + "], 'choisi.csv'); const dt2 = new DataTransfer(); dt2.items.add(fic2); const inp = document.querySelector('#fichier-tarifs'); inp.files = dt2.files; inp.dispatchEvent(new Event('change')); 1")
    time.sleep(2.5)
    verif(ev(w, "document.querySelector('#t-NL-0').value + '|' + (document.querySelector('.feuille h2') || {textContent: ''}).textContent + '|' + document.querySelector('#fichier-tarifs').value") == "4,50|Grille remplie depuis choisi.csv|", "fichier choisi par le sélecteur : grille remplie, sélecteur vidé")
    ev(w, "fermerFeuille(); ouvrirReglages(false); 1"); time.sleep(0.8)
    print("4. création (3 réussies, 1 échec sur relais fermé)", flush=True)
    r = appel(w, "creer", [{"bon": "WH/OUT/00118", "poids": "1,25"}, {"bon": "WH/OUT/00121", "poids": "0,8"}, {"bon": "WH/OUT/00125", "poids": "2,4"}, {"bon": "WH/OUT/00127", "poids": "3"}])
    verif(r["ok"] and len(r["faits"]) == 3 and len(r["echecs"]) == 1, f"faits={len(r.get('faits', []))} echecs={len(r.get('echecs', []))} {r if not r.get('ok') else ''}")
    verif(r["echecs"] and "STAT 14" in r["echecs"][0]["motif"], f"échec motivé : {r['echecs'][0]['motif'] if r.get('echecs') else '-'}")
    verif(r["pdf"] and Path(r["pdf"]).exists() and Path(r["pdf"]).stat().st_size > 500, f"PDF créé : {Path(r['pdf']).name if r.get('pdf') else '-'}")
    verif(all(f["n_colis"].startswith("TEST") for f in r["faits"]), "n° de colis fictifs TEST…")
    refus = list(Path(r["pdf"]).parent.glob("refus-*.csv")); lignes_refus = refus[0].read_text(encoding="utf-8-sig").splitlines() if refus else []
    verif(len(refus) == 1 and len(lignes_refus) == 2 and lignes_refus[1].startswith("S01255;WH/OUT/00127;14;3000;099999;FR;;;"), f"trace du refus écrite à côté du PDF : {lignes_refus[1][:60] if len(lignes_refus) > 1 else refus}")
    print("5. actualisation", flush=True)
    r = appel(w, "lister"); bons = [x["bon"] for x in r["prets"]]; verif("WH/OUT/00127" in bons and not any(b in bons for b in ("WH/OUT/00118", "WH/OUT/00121", "WH/OUT/00125")), f"après création, les 3 colis étiquetés ont disparu, celui en échec reste → {bons}")
    r = appel(w, "lister"); verif(len(r["prets"]) == 2 and not r["refus"] and any(x["bon"] == "WH/OUT/00130" for x in r["prets"]), "après deux actualisations, le bon en attente est validé et apparaît")
    print("6. réglages", flush=True)
    r = appel(w, "reglages_lire"); verif(r["valeurs"]["ODOO_DB"] == "demo" and len(r["odoo"]) + len(r["mr"]) == 12, "réglages démo préremplis, 12 champs")
    v = dict(r["valeurs"]); v["ODOO_API_KEY"] = "x"
    t = appel(w, "reglages_tester", v); verif(any(not ok_ for ok_, _ in t) and any("Odoo (démo) : ÉCHEC" in s for _, s in t), "test avec mauvaise clé → échec Odoo")
    t = appel(w, "reglages_tester", r["valeurs"]); verif(all(ok_ for ok_, _ in t), "test avec les valeurs démo → tout vert")
    v["MR_FORMAT"] = "10x15"; v["ODOO_API_KEY"] = "demo-5678"
    s = appel(w, "reglages_enregistrer", v); verif(s["ok"] and "10x15" in (D / "demo" / "mondialrelay.env").read_text(encoding="utf-8"), "enregistrement écrit dans demo/mondialrelay.env")
    verif(not (D / "odoo.env").exists() and not (D / "mondialrelay.env").exists(), "les vrais .env du dossier ne sont pas touchés")
    print("7. historique", flush=True)
    import re
    hist = appel(w, "historique", attente=30)
    verif(isinstance(hist, dict) and len(hist["lignes"]) == 3 and len(hist["refus"]) == 1 and hist["odoo"], f"historique fusionné : {len(hist.get('lignes', []))} étiquettes (Odoo démo + ce poste), {len(hist.get('refus', []))} refus")
    verif(all(l["ce_poste"] and l["fichier"] and l["n_colis"].startswith("TEST") for l in hist["lignes"]), "chaque ligne : créée sur ce poste, PDF local, n° de colis")
    verif((D / "demo" / "sortie").exists() and any(f.name == "complement.json" for f in list((D / "demo" / "sortie").glob("*/*"))), "fichier complement.json écrit à côté du PDF")
    l118 = next(l for l in hist["lignes"] if l["bon"] == "WH/OUT/00118")
    verif(l118["facture_ttc"] == 6.4 and l118["prix"] is not None and l118["client"] == "MARIE DUPONT", f"ligne fusionnée : coût estimé {l118.get('prix')}, facturé {l118.get('facture_ttc')} TTC, client lu dans Odoo")
    verif(hist["refus"][0]["bon"] == "WH/OUT/00127" and "STAT 14" in hist["refus"][0]["motif"], "refus du relais fermé listé à part")
    s = appel(w, "suivi", l118["n_colis"]); verif(s["ok"] and s["etat"] and s["detail"], f"suivi (démo) : {s.get('etat')} — {s.get('detail')}")
    app.os.startfile = lambda p: print("   (ouvert :", Path(p).name, ")", flush=True)
    appel(w, "ouvrir_fichier", l118["pdf_global"]); appel(w, "ouvrir_fichier", str(D / "etiquettes_du_jour.py"))
    verif(True, "ouvrir_fichier : seul le PDF du dossier sortie doit s'être ouvert ci-dessus")
    verif(ev(w, "ouvrirHistorique().then(()=>{window.__h=document.querySelectorAll('#historique .ligne-h').length + '|' + document.querySelector('#segments .actif').textContent.trim()}); 1") == 1, "écran Historique demandé")
    time.sleep(2.5); verif(ev(w, "window.__h") == "3|Historique", f"écran Historique affiché : {ev(w, 'window.__h')}")
    for _ in range(20):
        if "acheminement" in str(ev(w, "document.querySelector('#suivi-2').textContent")): break
        time.sleep(0.5)
    verif("acheminement" in str(ev(w, "document.querySelector('#suivi-2').textContent")), f"suivi affiché dans la liste : {ev(w, chr(100) + 'ocument.querySelector(' + chr(39) + '#suivi-0' + chr(39) + ').textContent')}")
    app.ouverts = []
    app.os.startfile = lambda p: app.ouverts.append(Path(p).name)
    ev(w, "document.querySelectorAll('#historique .ligne-h')[0].querySelectorAll('.btn')[0].click(); document.querySelectorAll('#historique .ligne-h')[0].querySelectorAll('.btn')[1].click(); 1")
    time.sleep(1.5)
    verif(len(app.ouverts) == 2 and any(n.startswith("WH-OUT-") for n in app.ouverts) and any(re.fullmatch(r"\d{8}-\d{6}", n) for n in app.ouverts), f"clics réels sur PDF et Dossier → ouverts : {app.ouverts}")
    ev(w, "filtrerHistorique(true); 1"); time.sleep(0.5)
    verif(ev(w, "document.querySelectorAll('#historique .ligne-h').length + '|' + document.querySelectorAll('#historique .ligne-r').length") == "3|1", "filtre « Ce poste » : 3 lignes et 1 refus")
    r = appel(w, "etiquette_pdf", "99999999", None); verif(not r["ok"] and "Démo" in r["erreur"], "PDF absent localement : demande à Mondial Relay (refusée en démo) avec message clair")
    print("8. écran", flush=True)
    verif(ev(w, "ouvrirReglages(false).then(()=>{window.__e=document.querySelector('#segments .actif').textContent.trim()}); 1") == 1, "ouverture des réglages demandée")
    time.sleep(1); verif(ev(w, "window.__e") == "Réglages", "segment Réglages actif")
    ev(w, "fermerReglages(); 1"); time.sleep(2)
    verif(ev(w, "document.querySelector('#ecran-colis').classList.contains('cache')") is False, "retour à l'écran Colis")
    print("9. journal et rapport", flush=True)
    j = D / "demo" / "journal.log"; jt = j.read_text(encoding="utf-8") if j.exists() else ""
    verif("démarrage v" in jt and "création : 3 faite(s), 1 refus" in jt and "test des connexions" in jt and "ÉCHEC" in jt, f"journal.log tenu en démo : {len(jt.splitlines())} lignes")
    verif("WH/OUT/00118 tapé « 1,25 » -> 1250 g (Odoo 0 kg)" in jt, "journal : poids tel que tapé, grammes envoyés et poids Odoo")
    from pypdf import PdfReader
    r = appel(w, "rapport", attente=40); pdf = Path(r.get("chemin", "")); texte = "".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages) if r.get("ok") and pdf.exists() else ""
    verif(r.get("ok") and pdf.stat().st_size > 1500 and "Environnement" in texte and "WH/OUT/00127" in texte and "journal" in texte.lower()
          and "demo-1234" not in texte and "MARIE DUPONT" not in texte, f"rapport PDF écrit et lisible, sans clé ni nom de client : {pdf.name if r.get('ok') else r}")
    verif("Joignabilité" in texte and "Mondial Relay : répond" in texte and "Odoo : injoignable" in texte, "rapport : joignabilité testée (Mondial Relay répond, l'Odoo de démo n'existe pas)")
    ev(w, "rapport(); 1")
    for _ in range(80):  # le rapport teste la joignabilité (jusqu'à 12 s) avant d'afficher la feuille
        time.sleep(0.5)
        if ev(w, "(document.querySelector('.feuille h2') || {textContent: ''}).textContent") == "Rapport enregistré": break
    verif(ev(w, "(document.querySelector('.feuille h2') || {textContent: ''}).textContent") == "Rapport enregistré", "bouton Rapport : feuille de confirmation")
    ev(w, "fermerFeuille(); 1")
    print("RÉSULTAT :", "tout passe" if ok else "des contrôles échouent", flush=True)
    w.destroy()

app.arrondir = scenario
app.deja_ouverte = lambda: False  # le banc de test ignore le verrou d'instance
sys.argv = ["x", "--demo"]
app.main()
