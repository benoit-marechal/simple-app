#!/usr/bin/env bash
set -euo pipefail

# Retrouver le projet Compose indépendamment du répertoire de lancement.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Lire le choix de stockage dans le fichier public de l'application.
source ./config.sh
if [[ "${STORAGE_MODE:-}" != text && "${STORAGE_MODE:-}" != postgres ]]; then
    printf 'Dans config.sh, STORAGE_MODE doit valoir text ou postgres.\n' >&2
    exit 1
fi

if [[ "${SESSION_STORAGE:-}" != memory && "${SESSION_STORAGE:-}" != file ]]; then
    printf 'Dans config.sh, SESSION_STORAGE doit valoir memory ou file.\n' >&2
    exit 1
fi
if [[ "${SESSION_COOKIE_SECURE:-}" != true && "${SESSION_COOKIE_SECURE:-}" != false ]]; then
    printf 'Dans config.sh, SESSION_COOKIE_SECURE doit valoir true ou false.\n' >&2
    exit 1
fi
if [[ "${APP_BIND:-}" != 127.0.0.1 && "${APP_BIND:-}" != 0.0.0.0 ]]; then
    printf 'Dans config.sh, APP_BIND doit valoir 127.0.0.1 ou 0.0.0.0.\n' >&2
    exit 1
fi
if [[ -z "${APP_HOSTS:-}" ]]; then
    printf 'Dans config.sh, APP_HOSTS doit contenir les noms ou IP autorisés.\n' >&2
    exit 1
fi

# Ne pas publier un formulaire de mot de passe en HTTP sur toutes les interfaces.
if [[ "${APP_BIND}" == 0.0.0.0 && "${SESSION_COOKIE_SECURE}" != true ]]; then
    printf 'Configurer HTTPS et SESSION_COOKIE_SECURE=true avant une publication réseau.\n' >&2
    exit 1
fi

# Transmettre uniquement les deux secrets optionnels par leur nom, sans les placer dans les arguments.
# Le conteneur temporaire crée les fichiers privés une seule fois ; les relances les conservent.
sudo --preserve-env=APP_PASSWORD,APP_SECRET_KEY docker run --rm --user 0 -e APP_PASSWORD -e APP_SECRET_KEY --volume "${PWD}/secrets:/credentials" simple-app-web python prepare_secrets.py

# Démarrer l'image déjà construite et attendre les services sains, au plus 120 s.
sudo STORAGE_MODE="${STORAGE_MODE}" SESSION_STORAGE="${SESSION_STORAGE}" SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE}" APP_BIND="${APP_BIND}" APP_HOSTS="${APP_HOSTS}" INSTANCE_HOSTNAME="$(hostname)" docker compose --profile "${STORAGE_MODE}" up -d --no-build --wait --wait-timeout 120
# En cas d'échec : sudo docker compose logs --tail=100 web db

# Vérifier la page et son stockage avant d'annoncer le démarrage réussi.
curl --fail --silent --show-error --max-time 15 http://localhost:8080/health >/dev/null
# Attendu : aucune sortie et aucun code d'erreur.
printf 'Application disponible sur cette VM : http://localhost:8080/\n'
printf 'Mot de passe commun à consulter localement : sudo cat secrets/password.txt\n'
