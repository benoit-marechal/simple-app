# Simple App

Un formulaire enregistre des messages dans un fichier texte ou PostgreSQL 16. La page affiche les messages, le login choisi et le hostname de la VM. Le web utilise Python 3.12, Flask, psycopg 3 et Gunicorn.

## Installer sur une VM Ubuntu 24.04

L’application écoute en HTTP sur le port 8080 et permet la connexion directement en HTTP. TLS est géré par un répartiteur externe (LB), dont la configuration est indépendante de ce dépôt. Sans LB HTTPS, le mot de passe et le cookie circulent en clair : réserver l’accès direct aux identifiants et messages de démonstration.

### Récupérer les sources depuis GitHub

Se connecter en SSH à la VM Ubuntu, généralement avec le compte `ubuntu`. Exécuter les commandes suivantes **sur cette VM**, avec un compte disposant de `sudo`, pour cloner le [dépôt GitHub public](https://github.com/benoit-marechal/simple-app) en HTTPS :

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /opt/simple-app
sudo chown "$(id -u):$(id -g)" /opt/simple-app
git clone https://github.com/benoit-marechal/simple-app.git /opt/simple-app
cd /opt/simple-app
```

Le dossier doit être vide au premier clone ; s’il contient déjà le dépôt, suivre la procédure de mise à jour plus bas.

### Configurer l’accès distant avant le déploiement

La configuration livrée publie le service sur `127.0.0.1`, pour un usage local. Sur la VM, ouvrir la configuration :

```bash
nano /opt/simple-app/config.sh
```

Dans `config.sh`, renseigner les valeurs suivantes :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
APP_BIND=0.0.0.0
```

Laisser `APP_HOSTS=` vide : aucune adresse IP n’est à renseigner pour installer ou déployer l’application.

### Autoriser l’accès réseau

Dans le **groupe de sécurité OpenStack attaché à la VM**, limiter l’accès au backend **TCP 8080** aux sources autorisées ou au LB lorsque celui-ci est raccordé. Vérifier qu’aucune autre règle attachée à la VM n’autorise déjà ce port depuis une origine plus large. Conserver l’accès SSH TCP 22 nécessaire à l’administration.

Les [ports publiés par Docker peuvent contourner les règles UFW](https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw) : le groupe de sécurité OpenStack doit porter la restriction d’origine effective.

### Installer, construire, déployer

Une fois la configuration distante enregistrée :

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

## Vérifier puis se connecter

Sur la VM :

```bash
cd /opt/simple-app
sudo docker compose ps
curl --fail http://127.0.0.1:8080/health
hostname
```

Le service web doit être sain et `/health` doit répondre HTTP 200. Ouvrir ensuite dans le navigateur l’adresse HTTP de la VM sur le port 8080, ou l’adresse du LB s’il est déjà raccordé.

Choisir un login et saisir le mot de passe commun de l’application. Il ne s’agit pas de comptes individuels avec des mots de passe distincts. Après connexion, la page affiche le login et le hostname de la VM : le comparer avec la commande `hostname`. `localhost` dans le navigateur désigne le poste utilisé, pas la VM distante.

Pour consulter le mot de passe, l’administrateur exécute sur la VM :

```bash
sudo cat /opt/simple-app/secrets/password.txt
```

Conserver cette valeur hors des dépôts et des échanges de diagnostic. Le conteneur web reçoit uniquement le hash du mot de passe et la clé de signature, montés en lecture seule ; le fichier du mot de passe en clair reste sur la VM.

## Configuration publique

Le fichier `config.sh`, à côté des scripts, contient les choix du déploiement. Ses valeurs livrées pour un usage local sont les suivantes ; sur une VM distante, appliquer les modifications de la procédure d’installation ci-dessus :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
APP_BIND=127.0.0.1
APP_HOSTS=
```

- `STORAGE_MODE=text` utilise `/data/messages.txt` dans le volume Docker `simple-app_messages_data`, local à cette instance. `postgres` démarre aussi PostgreSQL et utilise `simple-app_postgres_data`. Changer de mode ne transfère pas les messages.
- `SESSION_STORAGE=memory` garde les sessions côté serveur dans le processus web : un redémarrage déconnecte les utilisateurs. `file` utilise `/sessions` dans le volume local `simple-app_session_data` et conserve les sessions lors des redémarrages.
- `APP_BIND=127.0.0.1` limite la publication au poste ou à la VM. `0.0.0.0` publie le port 8080 sur les interfaces de l’hôte ; les restrictions réseau doivent alors être définies séparément.
- `APP_HOSTS=` vide accepte l’adresse d’accès sans filtrage de l’en-tête HTTP Host. Une liste facultative de noms ou d’IP séparés par des virgules active ce filtrage ; elle doit alors inclure les adresses d’accès ainsi que `localhost` et `127.0.0.1` pour les contrôles de santé. Le filtrage réseau ou au frontal reste nécessaire.

Le script transmet le hostname de la VM, et non celui du conteneur. Les sources et `config.sh` restent dans `/opt/simple-app` ; les messages et sessions sont dans les volumes Docker de cette VM. Les journaux sont ceux des conteneurs Docker.

Le cookie de session conserve `HttpOnly` et `SameSite=Lax`, sans attribut `Secure` émis par l’application. Si cette protection est souhaitée côté navigateur, le LB doit ajouter explicitement `Secure` aux cookies, s’il propose cette fonction ; terminer TLS ne l’ajoute pas automatiquement.

## Identifiants privés

`prepare_secrets.py` crée une clé aléatoire, un mot de passe aléatoire et son hash scrypt dans `secrets/`. Le répertoire a les droits `0700`, les fichiers `0600`, propriétaire UID/GID 1000. Le dossier est exclu de Git et du contexte de construction Docker.

Aucune valeur existante n’est remplacée lors d’une relance. Un ensemble incomplet provoque un arrêt : l’inspecter localement avant toute intervention, sans supprimer les identifiants d’un déploiement existant. L’application ne nécessite aucun fichier `.env`.

Avant le premier déploiement seulement, les variables exportées `APP_PASSWORD` et `APP_SECRET_KEY` permettent de fournir des valeurs communes à plusieurs VM. La clé doit contenir au moins 32 caractères. `deploy.sh` transmet uniquement ces deux variables à travers `sudo`, par leurs noms ; il ne place pas leurs valeurs dans la ligne de commande et ne les affiche pas. La politique `sudo` du compte doit autoriser leur conservation si cette option est utilisée.

Deux VM ayant des sessions locales nécessitent une affinité de session au répartiteur, aussi bien avec `memory` qu’avec `file`. Partager les clés ne partage pas les sessions. Un stockage de sessions sur NFS nécessite le mode `file`, le même stockage partagé et la même clé de signature ; ce montage n’est pas fourni.

Gunicorn utilise un seul processus et quatre threads. Ainsi, le mode mémoire représente bien la mémoire de cette instance ; plusieurs processus auraient chacun leurs propres sessions. Les fichiers de sessions utilisent le sérialiseur JSON de CacheLib, dans un répertoire réservé à cet usage.

Pour vérifier la persistance des sessions, se connecter, puis redémarrer le web :

```bash
sudo docker compose restart web
```

En mode `memory`, une nouvelle connexion est nécessaire. Pour vérifier le stockage sur disque, remplacer uniquement `SESSION_STORAGE=memory` par `SESSION_STORAGE=file` dans `config.sh`, lancer `bash deploy.sh`, se connecter à nouveau, puis redémarrer le web. La connexion est alors conservée. Changer de mode ne copie pas les anciennes sessions vers le nouveau stockage.

Le mot de passe commun doit contenir au moins 12 caractères. En l’absence de valeur fournie au premier déploiement, il est généré aléatoirement. Les relances ne le remplacent pas.

## Lancer en local avec Docker

Depuis ce dossier, avec un moteur Docker actif et Compose V2 :

```bash
docker compose build
docker run --rm --user 0 --volume "${PWD}/secrets:/credentials" simple-app-web python prepare_secrets.py
STORAGE_MODE=text SESSION_STORAGE=memory APP_BIND=127.0.0.1 APP_HOSTS= INSTANCE_HOSTNAME="$(hostname)" docker compose up -d --no-build --wait --wait-timeout 120
```

Pour PostgreSQL, utiliser `STORAGE_MODE=postgres` et ajouter `--profile postgres` à la commande Compose. Vérifier le backend avec `curl --fail http://localhost:8080/health`, puis ouvrir [http://localhost:8080/](http://localhost:8080/) dans le navigateur. Consulter localement `secrets/password.txt` avec les droits nécessaires.

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

Ces journaux sont les sorties stdout/stderr du conteneur, avec une rotation de trois fichiers de 10 Mio. Le projet ne crée pas de `/var/log/simple-app.log`. Les sorties d’un lancement par cloud-init se consultent séparément :

```bash
sudo tail -n 100 /var/log/cloud-init-output.log
sudo journalctl -u docker -n 100 --no-pager
```

En local, retirer `sudo` si le moteur Docker est accessible au compte utilisé. En mode texte :

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

## Sécurité et limites

Les formulaires de connexion, d’ajout et de déconnexion sont protégés contre les requêtes sans jeton CSRF. Les messages sont limités à 500 caractères, la liste à 1000 messages et le fichier à 1 Mio. Les tentatives de connexion et ajouts sont limités par IP et par instance. Plusieurs utilisateurs derrière la même IP partagent ces limites.

Le login libre identifie la session ; il ne prouve pas l’identité de l’utilisateur. La [revue OWASP](security_best_practices_report.md) documente les contrôles réalisés et les limites, dont le transport HTTP direct, le LB non recetté, les avis système résiduels et le rôle PostgreSQL de démonstration avant un usage Internet de ce mode.

## Arrêter, reprendre et changer de mode

```bash
sudo docker compose --profile postgres down
bash deploy.sh
```

`down` retire les conteneurs et le réseau en conservant les volumes et les identifiants privés. L’option `--volumes` supprimerait les données : ne pas l’ajouter pour un arrêt courant. Pour changer de stockage, arrêter avec la commande `down`, modifier `config.sh`, puis lancer `bash deploy.sh`.

## Mettre à jour depuis GitHub

Sur la VM, avec le même compte que pour le clone :

```bash
cd /opt/simple-app
cp -p config.sh "${HOME}/simple-app-config-$(date +%Y%m%d-%H%M%S).sh"
git status --short
git pull --ff-only
```

La copie conserve les choix de déploiement hors du dépôt. `git pull --ff-only` met à jour sans créer de commit de fusion. Si Git refuse parce que des modifications locales seraient écrasées, arrêter la procédure : conserver la copie et réconcilier les changements de `config.sh` avant de reprendre. Ne pas utiliser de remise à zéro forcée pour contourner ce refus.

Après un pull réussi, vérifier les valeurs de `config.sh`, puis reconstruire et redéployer :

```bash
nano /opt/simple-app/config.sh
bash build.sh
bash deploy.sh
curl --fail http://127.0.0.1:8080/health
```

Vérifier également l’accès depuis un poste autorisé. Les identifiants et les volumes existants sont conservés.

## Appel depuis cloud-init

Le clone HTTPS du dépôt public utilise la commande de la procédure d’installation. Une fois les sources présentes dans `/opt/simple-app` et `config.sh` adapté au déploiement distant, appeler les scripts ainsi :

```yaml
runcmd:
  - [bash, /opt/simple-app/install.sh]
  - [bash, /opt/simple-app/build.sh]
  - [bash, /opt/simple-app/deploy.sh]
```

Ce fragment lance l’installation, la construction et le déploiement HTTP. Configurer séparément les règles réseau et le LB. La configuration livrée dans Git reste locale par défaut.

Sources : paquets Ubuntu [Docker](https://packages.ubuntu.com/noble/docker.io), [Compose V2](https://packages.ubuntu.com/noble/docker-compose-v2), [Buildx](https://packages.ubuntu.com/noble/docker-buildx) et [commande Compose](https://docs.docker.com/reference/cli/docker/compose/up/).
