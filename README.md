# Simple App

Un formulaire enregistre des messages dans un fichier texte ou PostgreSQL 16. La page affiche les messages, le login choisi et le hostname de la VM. Le web utilise Python 3.12, Flask, psycopg 3 et Gunicorn.

## Installer sur Ubuntu 24.04

Les sources sont dans le [dépôt GitHub privé](https://github.com/benoit-marechal/simple-app). Pour éviter de placer un accès à ton compte GitHub sur une VM de TP, prépare une archive du commit depuis le Mac, dans le dossier du dépôt :

```bash
git archive --format=tar.gz --output=/tmp/simple-app.tar.gz HEAD
scp /tmp/simple-app.tar.gz "${VM_USER}@${VM_IP}:/tmp/simple-app.tar.gz"
```

`VM_USER` est ton compte SSH sur Ubuntu, généralement `ubuntu`. `VM_IP` est l’adresse SSH actuelle de la VM. Ces deux variables sont à définir sur le Mac avant le transfert. L’archive contient les sources versionnées ; elle ne contient ni le dossier `secrets/`, ni les données Docker, ni les accès GitHub.

Sur Ubuntu, extrais les sources :

```bash
sudo mkdir -p /opt/simple-app
sudo tar -xzf /tmp/simple-app.tar.gz -C /opt/simple-app
```

Place les sources complètes dans `/opt/simple-app`, puis lance avec un compte disposant de `sudo` :

```bash
cd /opt/simple-app
bash install.sh
bash build.sh
bash deploy.sh
```

- `install.sh` vérifie Ubuntu 24.04, installe `docker.io`, `docker-compose-v2`, `docker-buildx` et `curl`, puis active Docker. Le dépôt Ubuntu `universe` doit être activé.
- `build.sh` construit l’image web sans lancer l’application.
- `deploy.sh` génère les identifiants privés au premier lancement, conserve ceux déjà présents, démarre les services et vérifie `/health`.

Ces scripts peuvent être relancés : APT conserve les paquets installés, la construction réutilise son cache et Compose conserve les volumes. Les scripts ne configurent ni groupe Docker ni pare-feu.

## Se connecter

Ouvre [http://localhost:8080/](http://localhost:8080/) sur la machine qui héberge l’application. Choisis librement ton login et saisis le mot de passe commun du lab. Il ne s’agit pas de comptes individuels avec des mots de passe distincts.

Pour consulter le mot de passe, l’administrateur exécute localement :

```bash
sudo cat /opt/simple-app/secrets/password.txt
```

Conserve cette valeur hors des dépôts et des échanges de diagnostic. Le conteneur web reçoit uniquement le hash du mot de passe et la clé de signature, montés en lecture seule ; le fichier du mot de passe en clair reste sur la VM.

## Configuration publique

Le fichier `config.sh`, à côté des scripts, contient les choix du déploiement :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
SESSION_COOKIE_SECURE=false
APP_BIND=127.0.0.1
APP_HOSTS=localhost,127.0.0.1
```

- `STORAGE_MODE=text` utilise `/data/messages.txt` dans le volume Docker `simple-app_messages_data`, local à cette instance. `postgres` démarre aussi PostgreSQL et utilise `simple-app_postgres_data`. Changer de mode ne transfère pas les messages.
- `SESSION_STORAGE=memory` garde les sessions côté serveur dans le processus web : un redémarrage déconnecte les utilisateurs. `file` utilise `/sessions` dans le volume local `simple-app_session_data` et conserve les sessions lors des redémarrages.
- `SESSION_COOKIE_SECURE=false` permet le test HTTP local. Utilise `true` lorsque l’accès navigateur est réellement en HTTPS.
- `APP_BIND=127.0.0.1` limite la publication au poste ou à la VM. `0.0.0.0` publie le port 8080 sur les interfaces de l’hôte ; les restrictions réseau doivent alors être définies séparément.
- `APP_HOSTS` est la liste des noms ou IP acceptés dans l’en-tête HTTP Host, séparés par des virgules. Ajoute les noms réellement utilisés pour accéder à l’application.

Le script transmet le hostname de la VM, et non celui du conteneur. Les sources et `config.sh` restent dans `/opt/simple-app` ; les messages et sessions sont dans les volumes Docker de cette VM. Les journaux sont ceux des conteneurs Docker.

Ce dossier n’installe pas de terminaison TLS. L’accès Internet nécessite une configuration HTTPS et un contrôle de l’exposition du port 8080 avant ouverture.

Conserve `localhost` et `127.0.0.1` dans `APP_HOSTS` pour les contrôles de santé. Le script refuse `APP_BIND=0.0.0.0` avec un cookie non sécurisé. Activer ce cookie ne configure pas HTTPS : le proxy ou répartiteur TLS doit réellement être en place.

Pour un accès provisoire sécurisé depuis le Mac, sans ouvrir le port 8080 sur Internet, garde la configuration locale et utilise un tunnel SSH :

```bash
ssh -N -L 18080:127.0.0.1:8080 "${VM_USER}@${VM_IP}"
```

Ouvre ensuite `http://localhost:18080/` sur le Mac. La connexion entre le Mac et la VM passe dans le tunnel chiffré SSH. Ce tunnel individuel ne remplace pas la configuration d’accès HTTPS prévue pour les étudiants.

## Identifiants privés

`prepare_secrets.py` crée une clé aléatoire, un mot de passe aléatoire et son hash scrypt dans `secrets/`. Le répertoire a les droits `0700`, les fichiers `0600`, propriétaire UID/GID 1000. Le dossier est exclu de Git et du contexte de construction Docker.

Aucune valeur existante n’est remplacée lors d’une relance. Un ensemble incomplet provoque un arrêt : inspecte-le localement avant toute intervention, sans supprimer les identifiants d’un déploiement existant. L’application ne nécessite aucun fichier `.env`.

Avant le premier déploiement seulement, les variables exportées `APP_PASSWORD` et `APP_SECRET_KEY` permettent de fournir des valeurs communes à plusieurs VM. La clé doit contenir au moins 32 caractères. `deploy.sh` transmet uniquement ces deux variables à travers `sudo`, par leurs noms ; il ne place pas leurs valeurs dans la ligne de commande et ne les affiche pas. La politique `sudo` du compte doit autoriser leur conservation si cette option est utilisée.

Deux VM ayant des sessions locales nécessitent une affinité de session au répartiteur, aussi bien avec `memory` qu’avec `file`. Partager les clés ne partage pas les sessions. Un futur stockage de sessions sur NFS nécessiterait le mode `file`, le même stockage partagé et la même clé de signature ; ce montage n’est pas configuré ici.

Gunicorn utilise un seul processus et quatre threads. Ainsi, le mode mémoire représente bien la mémoire de cette instance ; plusieurs processus auraient chacun leurs propres sessions. Les fichiers de sessions utilisent le sérialiseur JSON de CacheLib, dans un répertoire réservé à cet usage.

Pour observer la différence, connecte-toi, puis redémarre le web :

```bash
sudo docker compose restart web
```

En mode `memory`, reconnecte-toi. Pour tester le disque, remplace uniquement `SESSION_STORAGE=memory` par `SESSION_STORAGE=file` dans `config.sh`, lance `bash deploy.sh`, connecte-toi à nouveau, puis refais le redémarrage. Cette fois la connexion est conservée. Changer de mode ne copie pas les anciennes sessions vers le nouveau stockage.

Le mot de passe commun doit contenir au moins 12 caractères. En l’absence de valeur fournie au premier déploiement, il est généré aléatoirement. Les relances ne le remplacent pas.

## Lancer en local avec Docker

Depuis ce dossier, avec un moteur Docker actif et Compose V2 :

```bash
docker compose build
docker run --rm --user 0 --volume "${PWD}/secrets:/credentials" simple-app-web python prepare_secrets.py
STORAGE_MODE=text SESSION_STORAGE=memory SESSION_COOKIE_SECURE=false APP_BIND=127.0.0.1 APP_HOSTS=localhost,127.0.0.1 INSTANCE_HOSTNAME="$(hostname)" docker compose up -d --no-build --wait --wait-timeout 120
```

Pour PostgreSQL, utilise `STORAGE_MODE=postgres` et ajoute `--profile postgres` à la commande Compose. Consulte localement `secrets/password.txt` avec les droits nécessaires, puis ouvre [http://localhost:8080/](http://localhost:8080/).

## Données et journaux

Sur Ubuntu, depuis `/opt/simple-app` :

```bash
sudo docker compose ps
curl --fail http://localhost:8080/health
sudo docker compose logs --tail=100 web
```

Pour suivre les requêtes et erreurs en direct :

```bash
sudo docker compose logs -f --tail=100 web
```

Ces journaux sont les sorties stdout/stderr du conteneur, avec une rotation de trois fichiers de 10 Mio. Le projet ne crée pas de `/var/log/simple-app.log`. Les sorties d’un futur lancement par cloud-init se consultent séparément :

```bash
sudo tail -n 100 /var/log/cloud-init-output.log
sudo journalctl -u docker -n 100 --no-pager
```

En local, retire `sudo` si ton moteur Docker est accessible à ton utilisateur. En mode texte :

```bash
sudo docker compose exec web cat /data/messages.txt
sudo docker volume inspect simple-app_messages_data --format '{{.Mountpoint}}'
```

Le fichier est créé au premier ajout ; chaque ligne contient un message et les retours à la ligne saisis sont remplacés par des espaces. En mode PostgreSQL :

```bash
sudo docker compose --profile postgres exec db psql -U simple_app -d simple_app -c 'SELECT id, contenu FROM messages ORDER BY id;'
sudo docker compose --profile postgres logs --tail=100 db
```

`init.sql` initialise la table lors du premier démarrage PostgreSQL avec un volume vide. Le mot de passe PostgreSQL de démonstration figure dans Compose ; la base n’a aucun port publié sur l’hôte.

Les sessions fichier sont dans `/sessions`, au sein du volume `simple-app_session_data`. Pour retrouver son répertoire sur la VM, sans afficher les sessions :

```bash
sudo docker volume inspect simple-app_session_data --format '{{.Mountpoint}}'
```

Les volumes nommés sont gérés par Docker, habituellement sous `/var/lib/docker/volumes/` sur Ubuntu. La commande `inspect` donne le chemin réel. Ils ne se trouvent pas dans le dossier des sources et ne sont pas copiés dans une archive Git.

## Limites de sécurité du TP

Les formulaires de connexion, d’ajout et de déconnexion sont protégés contre les requêtes sans jeton CSRF. Les messages sont limités à 500 caractères, la liste à 1000 messages et le fichier à 1 Mio. Les tentatives de connexion et ajouts sont limités par IP et par instance. Plusieurs étudiants derrière la même IP partagent ces limites.

Le login libre sert à observer la session ; il ne prouve pas une identité. Utilise des messages de test. La [revue OWASP](security_best_practices_report.md) documente les contrôles réalisés et les points restant à traiter, dont HTTPS, les avis système résiduels et le rôle PostgreSQL de démonstration avant un usage Internet de ce mode.

## Arrêter, reprendre et changer de mode

```bash
sudo docker compose --profile postgres down
bash deploy.sh
```

`down` retire les conteneurs et le réseau en conservant les volumes et les identifiants privés. L’option `--volumes` supprimerait les données : ne l’ajoute pas pour un arrêt courant. Pour changer de stockage, arrête avec la commande `down`, modifie `config.sh`, puis lance `bash deploy.sh`.

## Appel depuis cloud-init

Lorsque les sources complètes sont déjà présentes dans `/opt/simple-app` :

```yaml
runcmd:
  - [bash, /opt/simple-app/install.sh]
  - [bash, /opt/simple-app/build.sh]
  - [bash, /opt/simple-app/deploy.sh]
```

Sources : paquets Ubuntu [Docker](https://packages.ubuntu.com/noble/docker.io), [Compose V2](https://packages.ubuntu.com/noble/docker-compose-v2), [Buildx](https://packages.ubuntu.com/noble/docker-buildx) et [commande Compose](https://docs.docker.com/reference/cli/docker/compose/up/).
