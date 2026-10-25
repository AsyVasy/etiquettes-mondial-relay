"""Données d'exemple partagées par les captures avant/après (aucune connexion réseau)."""
def contexte():
    return {"o": type("O", (), {"db": "ma-boutique-prod"})(), "mr": {"MR_FORMAT": "A4"}, "ens": "BDTEST13", "cle": "x", "reel": True, "expe": {}}

def bon(i, name, origin):
    return {"id": i, "name": name, "origin": origin, "partner_id": [1, "x"], "carrier_tracking_ref": False, "shipping_weight": 0, "weight": 0, "state": "done"}

def p(nom, relais):
    return {"Dest_Ad1": nom, "LIV_Rel": relais, "LIV_Rel_Pays": "FR", "Poids": "15"}

PRETS = [
    (bon(1, "WH/OUT/00118", "S01234"), p("MARIE DUPONT", "036354"), "TABAC DE LA MAIRIE 75018 PARIS"),
    (bon(2, "WH/OUT/00121", "S01240"), p("JEAN MARTIN", "012871"), "PRESSING DU CANAL 59000 LILLE (changé)"),
    (bon(3, "WH/OUT/00125", "S01251"), p("SARL DURAND ET FILS", "078210"), "SUPERETTE DES LILAS 69007 LYON"),
]
REFUS = [(bon(4, "WH/OUT/00130", "S01260"), "bon pas encore validé")]
