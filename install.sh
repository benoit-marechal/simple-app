#!/usr/bin/env bash
set -euo pipefail

# Refuser un autre système avant toute installation de paquets.
if [[ ! -r /etc/os-release ]]; then
    printf 'Ce script nécessite Ubuntu 24.04.\n' >&2
    exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
    printf 'Ce script nécessite Ubuntu 24.04 ; système détecté : %s.\n' "${PRETTY_NAME:-inconnu}" >&2
    exit 1
fi

# Utiliser les sources à côté du script, quel que soit le répertoire de lancement.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -f docker-compose.yml ]]; then
    printf 'Le fichier docker-compose.yml doit être présent à côté du script.\n' >&2
    exit 1
fi

# Installer aussi OpenSSL pour la génération du certificat après le déploiement.
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 docker-buildx curl openssl
# Attendu : les paquets sont installés ; une erreur APT arrête le script.

# Démarrer Docker maintenant et le relancer automatiquement au démarrage de la VM.
sudo systemctl enable --now docker
