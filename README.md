# Simple App

Un formulaire enregistre des messages dans un fichier texte ou PostgreSQL 16. La page affiche les messages, le login choisi et le hostname de la VM. Le web utilise Python 3.12, Flask, psycopg 3 et Gunicorn.

## Installer sur une VM Ubuntu 24.04

L’application est accessible pendant le TP en HTTP sur l’IP publique de la VM, port 8080, sans DNS ni TLS. Le mot de passe, les messages et le cookie de session circulent en clair : utilise uniquement des identifiants et messages de démonstration, sur la durée du TP.

### Récupérer les sources depuis GitHub

Connecte-toi en SSH à la VM Ubuntu avec ton compte habituel, généralement `ubuntu`. Exécute les commandes suivantes **sur cette VM**, avec un compte disposant de `sudo`. Le [dépôt GitHub est privé](https://github.com/benoit-marechal/simple-app) : il faut lui donner un accès en lecture.

```bash
sudo apt-get update
sudo apt-get install -y git openssh-client
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
ssh-keygen -t ed25519 -f "${HOME}/.ssh/simple-app-deploy" -C "simple-app TP"
cat "${HOME}/.ssh/simple-app-deploy.pub"
```

Pour ce déploiement manuel, choisis une passphrase à la demande de `ssh-keygen` ; elle sera demandée lors des accès Git. Si cette clé existe déjà, conserve-la et affiche seulement son fichier `.pub` : ne l’écrase pas.

Dans GitHub, ouvre le dépôt → **Settings → Deploy keys → Add deploy key**. Donne un nom indiquant la VM, colle uniquement la clé publique affichée et laisse **Allow write access** décoché. Cette [clé de déploiement](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys) donne accès à ce seul dépôt. La clé privée reste sur la VM ; ne la copie pas dans Git, une conversation ou un fichier cloud-init. Révoque la clé dans GitHub à la fin du TP.

Clone ensuite les sources dans `/opt/simple-app` :

```bash
sudo mkdir -p /opt/simple-app
sudo chown "$(id -u):$(id -g)" /opt/simple-app
GIT_SSH_COMMAND="ssh -i ${HOME}/.ssh/simple-app-deploy -o IdentitiesOnly=yes" git clone git@github.com:benoit-marechal/simple-app.git /opt/simple-app
cd /opt/simple-app
```

Au premier accès, compare l’empreinte SSH annoncée avec les [empreintes officielles GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints), puis accepte-la si elle correspond. `GIT_SSH_COMMAND` sélectionne la clé dédiée pour cette commande ; `IdentitiesOnly=yes` évite de proposer d’autres clés. Le dossier doit être vide au premier clone ; s’il contient déjà le dépôt, utilise la procédure de mise à jour plus bas.

### Configurer l’accès distant avant le déploiement

Le fichier livré écoute sur `127.0.0.1`, pour un usage local. Sur la VM, renseigne son IP publique actuelle, puis ouvre la configuration :

```bash
printf 'IP publique de la VM : '
read -r VM_IP
printf 'APP_HOSTS=localhost,127.0.0.1,%s\n' "${VM_IP}"
nano /opt/simple-app/config.sh
```

Dans `config.sh`, saisis les valeurs suivantes :

```bash
STORAGE_MODE=text
SESSION_STORAGE=memory
SESSION_COOKIE_SECURE=false
APP_BIND=0.0.0.0
```

Remplace aussi la ligne `APP_HOSTS` par la ligne complète affichée par `printf`, qui contient l’IP réelle. Conserve `localhost` et `127.0.0.1` pour les contrôles de santé. Si l’IP publique change, modifie aussi `APP_HOSTS` puis relance `bash deploy.sh`.

### Autoriser le port du TP

Dans le **groupe de sécurité OpenStack attaché à la VM**, autorise le trafic entrant **TCP 8080** depuis l’IP publique du poste de test (`/32`) ou le CIDR public de la salle de TP. Vérifie qu’aucune autre règle attachée à la VM n’autorise déjà ce port depuis une origine plus large. Conserve l’accès SSH TCP 22 nécessaire à l’administration.

Si UFW est installé, vérifie son état :

```bash
sudo ufw status verbose
```

Seulement s’il est déjà actif et que sa politique l’exige, ajoute la règle pour la même origine :

```bash
printf 'CIDR public autorisé pour le TP : '
read -r TP_CIDR
sudo ufw allow from "${TP_CIDR}" to any port 8080 proto tcp
```

N’active pas UFW et ne modifie pas sa politique par défaut pour ce déploiement. Les [ports publiés par Docker peuvent contourner les règles UFW](https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw) : le groupe de sécurité OpenStack doit porter la restriction d’origine effective.

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

Le service web doit être sain et `/health` doit répondre sans erreur. Depuis ton poste, définis à nouveau `VM_IP` dans ce terminal puis teste :

```bash
printf 'IP publique de la VM : '
read -r VM_IP
curl --fail "http://${VM_IP}:8080/health"
printf 'Adresse à ouvrir dans le navigateur : http://%s:8080/\n' "${VM_IP}"
```

Ouvre cette adresse dans ton navigateur, choisis librement ton login et saisis le mot de passe commun du lab. Il ne s’agit pas de comptes individuels avec des mots de passe distincts. Après connexion, la page affiche le login et le hostname de la VM : compare-le avec la commande `hostname`.

`localhost` dans le navigateur désigne ton poste, pas la VM distante. Pour cet accès direct, utilise l’IP publique et le port **8080**.

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
SESSION_COOKIE_SECURE=false
APP_BIND=127.0.0.1
APP_HOSTS=localhost,127.0.0.1
```

- `STORAGE_MODE=text` utilise `/data/messages.txt` dans le volume Docker `simple-app_messages_data`, local à cette instance. `postgres` démarre aussi PostgreSQL et utilise `simple-app_postgres_data`. Changer de mode ne transfère pas les messages.
- `SESSION_STORAGE=memory` garde les sessions côté serveur dans le processus web : un redémarrage déconnecte les utilisateurs. `file` utilise `/sessions` dans le volume local `simple-app_session_data` et conserve les sessions lors des redémarrages.
- `SESSION_COOKIE_SECURE=false` permet l’accès HTTP du TP. Utilise `true` lorsque l’accès navigateur est réellement en HTTPS ; cette option seule ne met pas TLS en place.
- `APP_BIND=127.0.0.1` limite la publication au poste ou à la VM. `0.0.0.0` publie le port 8080 sur les interfaces de l’hôte ; les restrictions réseau doivent alors être définies séparément.
- `APP_HOSTS` est la liste des noms ou IP acceptés dans l’en-tête HTTP Host, séparés par des virgules. Ajoute les noms réellement utilisés pour accéder à l’application.

Le script transmet le hostname de la VM, et non celui du conteneur. Les sources et `config.sh` restent dans `/opt/simple-app` ; les messages et sessions sont dans les volumes Docker de cette VM. Les journaux sont ceux des conteneurs Docker.

Le TP utilise volontairement HTTP sans DNS ni TLS. Pour un usage durable ou des données réelles, prévois HTTPS. Le script accepte la publication réseau en HTTP et affiche un avertissement.

### Tunnel SSH facultatif

L’accès direct décrit ci-dessus n’a pas besoin de tunnel. Pour un accès individuel chiffré entre ton poste et la VM, tu peux garder `APP_BIND=127.0.0.1` avec `APP_HOSTS=localhost,127.0.0.1`. Sur ton poste, définis `VM_USER` avec ton compte SSH de la VM et `VM_IP` avec son IP publique, puis lance :

```bash
ssh -N -L 18080:127.0.0.1:8080 "${VM_USER}@${VM_IP}"
```

Ouvre ensuite `http://localhost:18080/` sur ton poste. **18080** est uniquement le port local de ce tunnel facultatif ; l’application reste publiée sur le port **8080** de la VM.

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

## Mettre à jour depuis GitHub

Sur la VM, avec le même compte que pour le clone :

```bash
cd /opt/simple-app
cp -p config.sh "${HOME}/simple-app-config-$(date +%Y%m%d-%H%M%S).sh"
git status --short
GIT_SSH_COMMAND="ssh -i ${HOME}/.ssh/simple-app-deploy -o IdentitiesOnly=yes" git pull --ff-only
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

Le dépôt étant privé, un `git clone` sans authentification échoue. Effectue d’abord le clone authentifié sur la VM avec la procédure ci-dessus, ou utilise un mécanisme de provisionnement qui fournit cet accès séparément. Ne place aucune clé privée ni aucun token dans les données utilisateur cloud-init.

Lorsque les sources complètes sont présentes dans `/opt/simple-app` et que `config.sh` contient déjà les valeurs du déploiement distant :

```yaml
runcmd:
  - [bash, /opt/simple-app/install.sh]
  - [bash, /opt/simple-app/build.sh]
  - [bash, /opt/simple-app/deploy.sh]
```

Ce fragment lance les trois étapes ; il ne prépare pas l’accès au dépôt privé ni les règles réseau. La configuration livrée dans Git reste locale par défaut.

Sources : paquets Ubuntu [Docker](https://packages.ubuntu.com/noble/docker.io), [Compose V2](https://packages.ubuntu.com/noble/docker-compose-v2), [Buildx](https://packages.ubuntu.com/noble/docker-buildx), [commande Compose](https://docs.docker.com/reference/cli/docker/compose/up/) et [variable Git GIT_SSH_COMMAND](https://git-scm.com/docs/git#Documentation/git.txt-codeGITSSHCOMMANDcode).
