# Étiquettes Mondial Relay

Outil Windows pour créer les étiquettes Mondial Relay des commandes Odoo d'un
commerçant (offre Start, compte prépayé) : liste des bons de livraison validés,
poids pesé, création des étiquettes, PDF unique à imprimer, numéros de colis
écrits dans Odoo.

- `etiquettes_du_jour.py` : moteur (Odoo XML-RPC, webservice Mondial Relay, PDF) et version console.
- `etiquettes_app.pyw` + `interface.html` : fenêtre principale (pywebview, WebView2).
- `reglages.pyw`, `etiquettes_fenetre.pyw` : interface classique tkinter, utilisée en secours.
- `demo.py` : mode démonstration, données locales, rien n'est envoyé.
- `Installer (une seule fois).bat` : installe Python s'il manque, les bibliothèques, les icônes, puis ouvre les réglages.

Installation et usage : voir `LISEZ-MOI.txt`. Les fichiers `odoo.env`,
`mondialrelay.env` et `tarifs.json` sont propres à chaque poste et ne sont pas
versionnés.

L'outil est générique : aucune donnée d'entreprise dans le code. Les fichiers
`*.env.exemple` préremplissent la fenêtre Réglages ; un déploiement peut y mettre
ses valeurs (site Odoo, base de production `ODOO_BASE_PROD`, enseigne, expéditeur)
et ajouter un raccourci `Odoo - colis Mondial Relay.url` que l'installateur copie
sur le Bureau s'il est présent.
