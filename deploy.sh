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
if [[ "${APP_BIND:-}" != 127.0.0.1 && "${APP_BIND:-}" != 0.0.0.0 ]]; then
    printf 'Dans config.sh, APP_BIND doit valoir 127.0.0.1 ou 0.0.0.0.\n' >&2
    exit 1
fi

# Transmettre uniquement les deux secrets optionnels par leur nom, sans les placer dans les arguments.
# Le conteneur temporaire crée les fichiers privés une seule fois ; les relances les conservent.
sudo --preserve-env=APP_PASSWORD,APP_SECRET_KEY docker run --rm --user 0 -e APP_PASSWORD -e APP_SECRET_KEY --volume "${PWD}/secrets:/credentials" simple-app-web python prepare_secrets.py

# Adapter aussi une base déjà remplie avant de démarrer le nouveau web.
# --single-transaction garde le verrou SQL jusqu'à la fin et annule tout en cas d'erreur.
if [[ "${STORAGE_MODE}" == postgres ]]; then
    sudo STORAGE_MODE="${STORAGE_MODE}" docker compose --profile postgres up -d --no-build --wait --wait-timeout 120 db
    sudo STORAGE_MODE="${STORAGE_MODE}" docker compose --profile postgres exec -T db \
        psql -X --single-transaction --file=- -v ON_ERROR_STOP=1 -U simple_app -d simple_app < migrate.sql
fi

# Démarrer l'image déjà construite et attendre les services sains, au plus 120 s.
sudo STORAGE_MODE="${STORAGE_MODE}" SESSION_STORAGE="${SESSION_STORAGE}" APP_BIND="${APP_BIND}" APP_HOSTS="${APP_HOSTS:-}" INSTANCE_HOSTNAME="$(hostname)" docker compose --profile "${STORAGE_MODE}" up -d --no-build --wait --wait-timeout 120
# En cas d'échec : sudo docker compose logs --tail=100 web db

# Vérifier la page et son stockage avant d'annoncer le démarrage réussi.
curl --fail --silent --show-error --max-time 15 http://localhost:8080/health >/dev/null
# Attendu : aucune sortie et aucun code d'erreur.
printf 'Contrôle local réussi : http://127.0.0.1:8080/health\n'
if [[ "${APP_BIND}" == 0.0.0.0 ]]; then
    printf 'Backend HTTP publié sur le port 8080 ; réserver son accès aux sources autorisées.\n'
else
    printf 'Backend HTTP accessible uniquement sur cet hôte : http://localhost:8080/\n'
fi
printf 'Mot de passe commun à consulter localement : sudo cat secrets/password.txt\n'
