const P = (v) => Promise.resolve(v);
const PRETS = [
  { bon: "WH/OUT/00118", commande: "S01234", client: "MARIE DUPONT", relais_num: "036354", relais: "TABAC DE LA MAIRIE 75018 PARIS", change: false, facture_ttc: 6.4 },
  { bon: "WH/OUT/00121", commande: "S01240", client: "JEAN MARTIN", relais_num: "012871", relais: "PRESSING DU CANAL 59000 LILLE (changé)", change: true, facture_ttc: 6.4 },
  { bon: "WH/OUT/00125", commande: "S01251", client: "SARL DURAND ET FILS", relais_num: "078210", relais: "SUPERETTE DES LILAS 69007 LYON", change: false, facture_ttc: 0 },
];
const CH_ODOO = [["ODOO_URL","Adresse du site Odoo","",""],["ODOO_DB","Nom de la base","« ma-boutique-prod » = production : vraies étiquettes payées. Toute autre base = simulation.",""],["ODOO_USER","Identifiant Odoo","L'e-mail de connexion à Odoo de la personne qui utilise l'outil.",""],["ODOO_API_KEY","Clé API Odoo","Dans Odoo, avec ce compte : nom en haut à droite > Mon profil > onglet Sécurité du compte > Nouvelle clé API. Choisir la durée la plus longue proposée et noter la date de fin. La clé ne s'affiche qu'une fois : la coller ici tout de suite.","secret"]];
const CH_MR = [["MR_ENSEIGNE","Code enseigne","Code à 8 caractères du compte Mondial Relay (Offre Start).",""],["MR_CLE_PRIVEE","Clé privée","mondialrelay.fr > Mon profil > Mes paramètres de connexion > Webservices.","secret"],["MR_EXPE_NOM","Nom de l'expéditeur","Imprimé sur l'étiquette.",""],["MR_EXPE_TEL","Téléphone de l'expéditeur","10 chiffres, ex. 0199001234.",""],["MR_EXPE_MAIL","E-mail de l'expéditeur","",""],["MR_FORMAT","Format d'impression","A4 ou A5 = imprimante classique ; 10x15 = imprimante à étiquettes.","format"],["MR_DEPUIS","Premier jour d'utilisation","AAAA-MM-JJ. Les colis validés dans Odoo avant cette date ne sont jamais repris.","date"]];
window.pywebview = { api: {
  info: () => P({ installation: false, complet: true }),
  demarrer: () => P({ ok: true, reel: true, db: "ma-boutique-prod" }),
  lister: () => P({ ok: true, prets: PRETS, refus: [{ bon: "WH/OUT/00130", commande: "S01260", motif: "bon pas encore validé" }] }),
  verifier_poids: (lignes) => { const kg = {}, fautes = [], prix = {}; for (const l of lignes) { const v = parseFloat((l.poids || "").replace(",", ".")); if (!(v > 0) || v > 30) fautes.push(l.bon); else { kg[l.bon] = v; prix[l.bon] = v <= 1 ? 5.5 : v <= 2 ? 6.3 : null; } } return P({ kg, fautes, prix, grille_date: "2026-01-01" }); },
  tarifs_lire: () => P({ date: "2026-01-01", tranches: [500, 2000, 4000, 6000, 8000, 10000, 15000, 20000, 25000, 30000], pays: { FR: [6.4, 8.5, 9.6, 12.2, 15.2, 16.9, 23.9, 26.9, 35.05, null], BE: Array(10).fill(null), LU: Array(10).fill(null), NL: Array(10).fill(null), ES: Array(10).fill(null), PT: Array(10).fill(null), DE: Array(10).fill(null) } }),
  tarifs_publique: () => P({ date: "2026-01-07", tranches: [500, 1000, 2000, 4000, 10000, 20000, 25000, 30000], pays: {}, paliers: ["0 à 9 colis par mois (prix public)", "10 à 49 colis par mois (-4 %)", "50 à 99 colis par mois (-7 %)", "100 à 249 colis par mois (-9 %)", "250 colis et plus par mois (-10 %)"] }),
  tarifs_enregistrer: () => P({ ok: true }),
  creer: () => P({ ok: true, pdf: "x", faits: [], echecs: [] }),
  rapport: () => P({ ok: true, chemin: "C:/EtiquettesMR/sortie/rapport-20261028-120000.pdf", dossier: "C:/EtiquettesMR/sortie" }),
  reglages_lire: () => P({ valeurs: { ODOO_URL: "https://odoo.exemple.fr", ODOO_DB: "ma-boutique-prod", ODOO_USER: "prenom.nom@exemple.fr", ODOO_API_KEY: "0123456789abcdef0123456789abcdef01234567", MR_ENSEIGNE: "BDTEST13", MR_CLE_PRIVEE: "exemple", MR_EXPE_NOM: "MA BOUTIQUE", MR_EXPE_TEL: "0199001234", MR_EXPE_MAIL: "expedition@exemple.fr", MR_FORMAT: "A4", MR_DEPUIS: "2026-10-22" }, odoo: CH_ODOO, mr: CH_MR }),
  reglages_verifier: () => P([]),
  reglages_tester: () => P([[true, "Odoo : connecté en tant que Prénom Nom."], [true, "Odoo : base de PRODUCTION → vraies étiquettes, payées."], [true, "Odoo : droit d'écrire les n° de colis dans les bons : OK."], [false, "Mondial Relay : ÉCHEC — STAT 97 clé de sécurité invalide."]]),
  fermer: () => P(), reduire: () => P(), agrandir: () => P(), ouvrir_fichier: () => P(),
  historique: () => P({ jours: 30, odoo: true, erreur: "", lignes: [
    { date: "2026-10-23 09:48:12", commande: "S01234", bon: "WH/OUT/00118", client: "MARIE DUPONT", relais: "TABAC DE LA MAIRIE 75018 PARIS", poids_g: "1250", n_colis: "12345678", fichier: "x", dossier: "x", prix: 6.3, facture_ttc: 6.4, ce_poste: true },
    { date: "2026-10-23 09:48:12", commande: "S01240", bon: "WH/OUT/00121", client: "JEAN MARTIN", relais: "PRESSING DU CANAL 59000 LILLE", poids_g: "800", n_colis: "12345679", fichier: "x", dossier: "x", prix: 5.5, facture_ttc: 0, ce_poste: true },
    { date: "2026-10-22 17:12:40", commande: "S01198", bon: "WH/OUT/00102", client: "AHMED BENALI", relais: "", poids_g: "", n_colis: "12345601", fichier: null, dossier: null, prix: null, facture_ttc: null, ce_poste: false },
  ], refus: [ { date: "2026-10-23 09:48:12", bon: "WH/OUT/00127", commande: "S01255", stat: "14", poids_g: "3000", motif: "Mondial Relay STAT 14 n° de point relais invalide" } ] }),
  suivi: (num) => P(num === "12345601" ? { ok: true, etat: "Livré", detail: "Colis livré le 24/10/26 à 11:02" } : { ok: true, etat: "En cours d'acheminement", detail: "Prise en charge point relais le 23/10/26 à 15:10, Villeneuve" }),
  etiquette_pdf: () => P({ ok: true, chemin: "x", local: true }),
}};
window.addEventListener("load", async () => {
  await new Promise((r) => setTimeout(r, 300));
  etat.poids["WH/OUT/00118"] = "1,25"; etat.poids["WH/OUT/00121"] = "0,80"; afficher();
  const sc = document.documentElement.dataset.scenario;
  if (sc === "colis") { document.querySelector("#poids-2 input").focus(); }
  if (sc === "colis-decoche") { basculer("WH/OUT/00121"); document.querySelector("#poids-2 input").focus(); }
  if (sc === "colis-survol") { document.querySelector("#poids-2 input").blur(); document.querySelectorAll(".relais")[1].classList.add("survol"); document.head.insertAdjacentHTML("beforeend", "<style>.relais.survol{background:var(--champ);color:var(--txt)} .relais.survol .crayon{color:var(--accent)}</style>"); }
  if (sc === "confirmation") { etat.poids["WH/OUT/00125"] = "2,40"; afficher(); demanderCreation(); }
  if (sc === "reglages") { await ouvrirReglages(false); await new Promise((r) => setTimeout(r, 200)); testerReglages(); document.activeElement.blur(); }
  if (sc === "reglages-echec") { window.pywebview.api.reglages_tester = () => P([[false, "Odoo : ÉCHEC — connexion refusée : identifiant, clé API ou nom de base incorrect (ou clé expirée)"], [false, "Mondial Relay : ÉCHEC — STAT 97 clé de sécurité invalide."]]); await ouvrirReglages(false); await new Promise((r) => setTimeout(r, 200)); testerReglages(); document.activeElement.blur(); }
  if (sc === "historique") { await ouvrirHistorique(); }
  if (sc === "historique-recherche") { await ouvrirHistorique(); const c = document.querySelector("#h-recherche"); c.value = "dupont"; rechercherHistorique("dupont"); c.focus(); }
  if (sc === "tarifs") { await ouvrirTarifs(); document.querySelector("#t-palier").value = "1"; document.activeElement.blur(); }
  if (sc === "reglages-points") { await ouvrirReglages(false); await new Promise((r) => setTimeout(r, 200)); voir("r-ODOO_API_KEY", document.querySelector("#r-ODOO_API_KEY").nextElementSibling); document.activeElement.blur(); }
  if (sc === "reglages-aide") { await ouvrirReglages(false); await new Promise((r) => setTimeout(r, 200)); document.getElementById("r-ODOO_API_KEY").focus(); }
});
document.head.insertAdjacentHTML("beforeend", "<style>*{transition:none!important;animation:none!important}</style>");
