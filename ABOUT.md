Application web Python avec authentification, liste de messages, hostname de l’instance, stockage texte ou PostgreSQL et sessions côté serveur.

- [README.md](README.md) · Commandes de lancement, d’installation sur Ubuntu 24.04 et d’exploitation.
- [app.py](app.py) · Gère la connexion et les sessions, lit et ajoute les messages, puis affiche la liste et le hostname de l’hôte.
- [messages.py](messages.py) · Enregistre la date, l’heure de Paris et le login avec chaque nouveau message ; conserve les verrous, les limites et les requêtes SQL paramétrées.
- [session_files.py](session_files.py) · Sélectionne le sérialiseur JSON pour les sessions stockées sur disque.
- [docker-compose.yml](docker-compose.yml) · Lance le web, monte ses identifiants privés en lecture seule et conserve les volumes de messages, de sessions et de PostgreSQL optionnel.
- [Dockerfile](Dockerfile) · Construit l’image Python et lance Gunicorn.
- [requirements.txt](requirements.txt) · Versions des dépendances Python de stockage, d’authentification et de formulaires.
- [init.sql](init.sql) · Crée la table et deux messages lors de l’initialisation d’une base vide.
- [migrate.sql](migrate.sql) · Adapte la contrainte de longueur PostgreSQL au préfixe des messages, sans modifier les lignes existantes.
- [test_messages.py](test_messages.py) · Vérifie le format des nouveaux messages, la conservation des anciens et les limites du fichier texte.
- [install.sh](install.sh) · Installe Docker et Compose sur Ubuntu 24.04 et active le service Docker.
- [build.sh](build.sh) · Construit l’image Python sans démarrer l’application.
- [deploy.sh](deploy.sh) · Prépare les identifiants au premier lancement, démarre les services selon la configuration et vérifie leur santé HTTP.
- [prepare_secrets.py](prepare_secrets.py) · Génère une seule fois les fichiers privés de signature et de mot de passe dans le dossier de déploiement exclu de Git.
- [config.sh](config.sh) · Choisit le stockage des messages et sessions, la publication réseau et le filtrage Host facultatif.
- [VERSION](VERSION) · Version de l’application.
- [security_best_practices_report.md](security_best_practices_report.md) · Revue OWASP, tests de sécurité et limites de validation de l’exposition Internet.
- [templates/](templates/ABOUT.md) · Pages HTML de connexion et de messages.
