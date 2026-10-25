# Outils de développement

Rien ici n'est installé chez l'utilisateur.

- `test_demo.py` : banc de test complet. Ouvre la vraie fenêtre pywebview en mode démo
  et parcourt toutes les interactions par le pont JavaScript (liste, relais, poids,
  grille tarifaire, fichiers déposés, création, historique, réglages). Le PDF n'est pas
  ouvert à l'écran. Usage : `py -3 -X utf8 test_demo.py <dossier du dépôt>` ; la dernière
  ligne doit être `RÉSULTAT : tout passe`. Durée : une à deux minutes.
- `donnees_exemple.py` : données partagées par d'anciens bancs tkinter (conservé pour mémoire).
- `mock.js` : faux `window.pywebview.api` pour afficher `interface.html` dans un navigateur
  sans Python ; porte les scénarios de capture.
- `rendu_maquette.py` : capture PNG d'un écran avec Edge sans fenêtre, via `mock.js`.

Le mode démo de l'outil lui-même (`Etiquettes - mode demo.bat`) reste le moyen de
tester à la main.
