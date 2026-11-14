# Simple App

Un formulaire enregistre des messages dans un fichier texte ou PostgreSQL 16. La page affiche les messages, le login choisi et le hostname de la VM. Le web utilise Python 3.12, Flask, psycopg 3 et Gunicorn.

## Installer sur une VM Ubuntu 24.04

Le backend écoute en HTTP sur le port 8080. Le cookie de session porte toujours l’attribut `Secure` : l’accès authentifié distant nécessite un accès HTTPS raccordé séparément par l’administrateur. Les scripts préparent l’application et le certificat ; ils ne configurent pas la terminaison TLS. Utilise uniquement des identifiants et messages de démonstration pour ce TP.

### Récupérer les sources depuis GitHub

Connecte-toi en SSH à la VM Ubuntu avec ton compte habituel, généralement `ubuntu`. Exécute les commandes suivantes **sur cette VM**, avec un compte disposant de `sudo`, pour cloner le [dépôt GitHub public](https://github.com/benoit-marechal/simple-app) en HTTPS :

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /opt/simple-app
sudo chown "$(id -u):$(id -g)" /opt/simple-app
git clone https://github.com/benoit-marechal/simple-app.git /opt/simple-app
cd /opt/simple-app
```

Le dossier doit être vide au premier clone ; s’il contient déjà le dépôt, utilise la procédure de mise à jour plus bas.

### Configurer l’accès distant avant le déploiement

Le fichier livré écoute sur `127.0.0.1`, pour un usage local. Sur la VM, ouvre la configuration :

```bash
nano /opt/simple-app/config.sh
```

Dans `config.sh`, saisis les valeurs suivantes :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
APP_BIND=0.0.0.0
```

Laisse `APP_HOSTS=` vide : aucune adresse IP n’est à renseigner pour installer ou déployer l’application, ni pour générer son certificat.

### Autoriser le port du TP

Dans le **groupe de sécurité OpenStack attaché à la VM**, limite l’accès au backend **TCP 8080** aux sources autorisées pour les contrôles ou au frontal HTTPS, selon ton raccordement TLS. Vérifie qu’aucune autre règle attachée à la VM n’autorise déjà ce port depuis une origine plus large. Conserve l’accès SSH TCP 22 nécessaire à l’administration.

Les [ports publiés par Docker peuvent contourner les règles UFW](https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw) : le groupe de sécurité OpenStack doit porter la restriction d’origine effective.

### Installer, construire, déployer

Une fois la configuration distante enregistrée :

```bash
cd /opt/simple-app
bash install.sh
bash build.sh
bash deploy.sh
bash gen-certif.sh
```

- `install.sh` vérifie Ubuntu 24.04, installe `docker.io`, `docker-compose-v2`, `docker-buildx`, `curl` et `openssl`, puis active Docker. Le dépôt Ubuntu `universe` doit être activé.
- `build.sh` construit l’image web sans lancer l’application.
- `deploy.sh` génère les identifiants privés au premier lancement, conserve ceux déjà présents, démarre les services et vérifie `/health`.
- `gen-certif.sh` génère un certificat autosigné générique, sans saisie, argument ni adresse IP. Il prépare les fichiers sans activer HTTPS.

Ces scripts peuvent être relancés : APT conserve les paquets installés, la construction réutilise son cache et Compose conserve les volumes. Les scripts ne configurent ni groupe Docker ni pare-feu.

### Certificat autosigné

Exécute `gen-certif.sh` sur la VM :

```bash
cd /opt/simple-app
bash gen-certif.sh
```

Le certificat générique utilise `CN=Simple App`, une clé RSA de 3072 bits, une signature SHA-256 et une validité de 30 jours. Il ne contient aucune extension SAN ni adresse IP. Sa génération ne demande ni saisie ni argument.

- `/opt/simple-app/certs/server.crt` : certificat public, dont l’empreinte SHA-256 et les dates sont affichées par le script. Tu peux partager le certificat et son empreinte pour vérifier son identité.
- `/opt/simple-app/certs/server.key` : clé privée, avec les droits `0600`, dans le dossier `certs/` en `0700`. Ne la partage pas et ne la copie pas dans Git, cloud-init ou un échange de diagnostic. Le dossier est exclu de Git et du contexte de construction Docker.

Une paire existante valide est conservée, sans écrasement, y compris un ancien certificat contenant des IP. Pour obtenir le nouveau certificat générique, renouvelle cette paire manuellement. Une paire incomplète, invalide ou expirée provoque un arrêt. Le renouvellement est manuel : déplace le dossier `certs/` entier dans une archive privée, en conservant ses droits, puis relance la génération. Le script crée un nouveau dossier ; il refuse aussi de réutiliser un dossier vide déjà présent. Un changement d’IP ne demande pas de régénérer ce certificat générique.

Le navigateur signalera deux problèmes distincts : le certificat autosigné n’est pas reconnu par une autorité de confiance, et son nom générique ne correspond pas à l’adresse IP de la VM. Accepter une exception de confiance ne corrige pas la correspondance du nom. Ce certificat sert au TP ; il ne fournit pas une identité serveur validée pour un usage réel.

Avant d’accepter une exception dans le navigateur, compare l’empreinte SHA-256 du certificat présenté avec celle lue sur la VM par SSH :

```bash
openssl x509 -in /opt/simple-app/certs/server.crt -noout -fingerprint -sha256
```

La génération seule ne chiffre pas le trafic : le certificat et sa clé doivent être raccordés au service HTTPS. Le cookie de session porte toujours l’attribut `Secure`, imposé dans le code de l’application. HTTPS est donc nécessaire au fonctionnement des sessions dans le navigateur.

## Vérifier puis se connecter

Sur la VM :

```bash
cd /opt/simple-app
sudo docker compose ps
curl --fail http://127.0.0.1:8080/health
hostname
```

Le service web doit être sain et `/health` doit répondre HTTP 200. Ce contrôle valide uniquement le backend. Raccorde le certificat et sa clé à ton service HTTPS, puis ouvre son adresse HTTPS pour te connecter : le cookie `Secure` nécessite HTTPS pour l’accès authentifié distant.

Une fois l’accès HTTPS opérationnel, choisis librement ton login et saisis le mot de passe commun du lab. Il ne s’agit pas de comptes individuels avec des mots de passe distincts. Après connexion, la page affiche le login et le hostname de la VM : compare-le avec la commande `hostname`. `localhost` dans le navigateur désigne ton poste, pas la VM distante.

Pour consulter le mot de passe, l’administrateur exécute sur la VM :

```bash
sudo cat /opt/simple-app/secrets/password.txt
```

Conserve cette valeur hors des dépôts et des échanges de diagnostic. Le conteneur web reçoit uniquement le hash du mot de passe et la clé de signature, montés en lecture seule ; le fichier du mot de passe en clair reste sur la VM.

## Configuration publique

Le fichier `config.sh`, à côté des scripts, contient les choix du déploiement. Ses valeurs livrées pour un usage local sont les suivantes ; sur une VM distante, applique les modifications de la procédure d’installation ci-dessus :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
APP_BIND=127.0.0.1
APP_HOSTS=
```

- `STORAGE_MODE=text` utilise `/data/messages.txt` dans le volume Docker `simple-app_messages_data`, local à cette instance. `postgres` démarre aussi PostgreSQL et utilise `simple-app_postgres_data`. Changer de mode ne transfère pas les messages.
- `SESSION_STORAGE=memory` garde les sessions côté serveur dans le processus web : un redémarrage déconnecte les utilisateurs. `file` utilise `/sessions` dans le volume local `simple-app_session_data` et conserve les sessions lors des redémarrages.
- Le cookie de session porte toujours l’attribut `Secure`. Ce comportement est fixé dans le code et ne peut pas être désactivé dans `config.sh`, Compose ou une variable d’environnement. L’accès navigateur doit être en HTTPS pour conserver la session.
- `APP_BIND=127.0.0.1` limite la publication au poste ou à la VM. `0.0.0.0` publie le port 8080 sur les interfaces de l’hôte ; les restrictions réseau doivent alors être définies séparément.
- `APP_HOSTS=` vide accepte l’adresse utilisée pour accéder au TP, sans filtrage de l’en-tête HTTP Host. Pour un usage avancé, une liste facultative de noms ou d’IP séparés par des virgules active ce filtrage ; elle doit alors inclure les adresses d’accès ainsi que `localhost` et `127.0.0.1` pour les contrôles de santé. Le filtrage réseau ou au frontal reste nécessaire.

Le script transmet le hostname de la VM, et non celui du conteneur. Les sources et `config.sh` restent dans `/opt/simple-app` ; les messages et sessions sont dans les volumes Docker de cette VM. Les journaux sont ceux des conteneurs Docker.

`deploy.sh` rappelle que le backend HTTP ne suffit pas à l’accès authentifié distant. Pour un usage durable ou des données réelles, utilise un certificat approuvé dont le nom correspond à l’adresse HTTPS.

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
STORAGE_MODE=text SESSION_STORAGE=memory APP_BIND=127.0.0.1 APP_HOSTS= INSTANCE_HOSTNAME="$(hostname)" docker compose up -d --no-build --wait --wait-timeout 120
```

Pour PostgreSQL, utilise `STORAGE_MODE=postgres` et ajoute `--profile postgres` à la commande Compose. Vérifie le backend avec `curl --fail http://localhost:8080/health`. Le certificat se génère avec `bash gen-certif.sh` ; son raccordement HTTPS est à réaliser séparément pour l’accès navigateur. Consulte localement `secrets/password.txt` avec les droits nécessaires.

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

Le login libre sert à observer la session ; il ne prouve pas une identité. Utilise des messages de test. La [revue OWASP](security_best_practices_report.md) documente les contrôles réalisés et les limites, dont l’absence de recette HTTPS, les avis système résiduels et le rôle PostgreSQL de démonstration avant un usage Internet de ce mode.

## Arrêter, reprendre et changer de mode

```bash
sudo docker compose --profile postgres down
bash deploy.sh
```

`down` retire les conteneurs et le réseau en conservant les volumes et les identifiants privés. L’option `--volumes` supprimerait les données : ne l’ajoute pas pour un arrêt courant. Pour changer de stockage, arrête avec la commande `down`, modifie `config.sh`, puis lance `bash deploy.sh`.

## Mettre à jour depuis GitHub

Sur la VM, avec le même compte que pour le clone :

```bash
cd /opt/simple-app
cp -p config.sh "${HOME}/simple-app-config-$(date +%Y%m%d-%H%M%S).sh"
git status --short
git pull --ff-only
```

La copie conserve tes choix de déploiement hors du dépôt. `git pull --ff-only` met à jour sans créer de commit de fusion. Si Git refuse parce que tes modifications locales seraient écrasées, arrête la procédure : garde la copie et réconcilie les changements de `config.sh` avant de reprendre. N’utilise pas de remise à zéro forcée pour contourner ce refus.

Après un pull réussi, vérifie les valeurs de `config.sh`, puis reconstruis et redéploie :

```bash
nano /opt/simple-app/config.sh
bash build.sh
bash deploy.sh
curl --fail http://127.0.0.1:8080/health
```

Relance aussi le contrôle depuis ton poste. Les identifiants et les volumes existants sont conservés.

## Appel depuis cloud-init

Le clone HTTPS du dépôt public utilise la commande de la procédure d’installation. Une fois les sources présentes dans `/opt/simple-app` et `config.sh` adapté au déploiement distant, appelle les scripts ainsi :

```yaml
runcmd:
  - [bash, /opt/simple-app/install.sh]
  - [bash, /opt/simple-app/build.sh]
  - [bash, /opt/simple-app/deploy.sh]
```

Ce fragment lance l’installation, la construction et le déploiement. Configure séparément les règles réseau, génère ensuite le certificat avec `bash gen-certif.sh` et raccorde ton service HTTPS. La configuration livrée dans Git reste locale par défaut.

Sources : paquets Ubuntu [Docker](https://packages.ubuntu.com/noble/docker.io), [Compose V2](https://packages.ubuntu.com/noble/docker-compose-v2), [Buildx](https://packages.ubuntu.com/noble/docker-buildx) et [commande Compose](https://docs.docker.com/reference/cli/docker/compose/up/).
