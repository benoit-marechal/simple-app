#!/usr/bin/env bash
set -euo pipefail

# Utiliser les sources à côté du script, quel que soit le répertoire de lancement.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -f docker-compose.yml ]]; then
    printf 'Le fichier docker-compose.yml doit être présent à côté du script.\n' >&2
    exit 1
fi

# Détecter les commandes nécessaires avant et après l'installation.
# Sans ce contrôle, une ancienne version de Compose peut échouer au déploiement.
docker_compatible() {
    local compose_help
    command -v docker >/dev/null || return 1
    compose_help=$(sudo docker compose up --help 2>/dev/null) || return 1
    [[ "${compose_help}" == *--wait-timeout* ]] &&
        sudo docker buildx version >/dev/null 2>&1
}

if ! docker_compatible || ! command -v curl >/dev/null; then
    if ! command -v apt-get >/dev/null; then
        printf 'Installer Docker Engine, les plugins Compose et Buildx, et curl avec le gestionnaire de paquets du système, puis relancer.\n' >&2
        exit 1
    fi

    sudo apt-get update
    if docker_compatible; then
        sudo apt-get install -y curl
    else
        # Ubuntu fournit Compose v2 sous un autre nom que Debian.
        compose_package=docker-compose
        if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
            compose_package=docker-compose-v2
        fi
        compose_version=$(LC_ALL=C apt-cache policy "${compose_package}" | awk '/Candidate:/ {print $2}')
        if ! dpkg-query -W -f='${Status}\n' docker-ce 2>/dev/null | grep -qx 'install ok installed' &&
            [[ -n "${compose_version}" && "${compose_version}" != '(none)' ]] &&
            dpkg --compare-versions "${compose_version}" ge 2 &&
            apt-cache show docker-buildx >/dev/null 2>&1; then
            sudo apt-get --no-remove install -y docker.io "${compose_package}" docker-buildx curl
        else
            # Certaines suites APT ne fournissent que Compose v1 ou aucun Buildx.
            # La suite du dépôt Docker correspond à celle déclarée par l'hôte.
            if ! apt-cache show docker-compose-plugin >/dev/null 2>&1 ||
                ! apt-cache show docker-buildx-plugin >/dev/null 2>&1; then
                source /etc/os-release
                case "${ID:-}" in
                    debian|ubuntu) ;;
                    *)
                        printf 'Les dépôts APT ne fournissent pas les plugins requis. Installer Compose et Buildx pour ce système, puis relancer.\n' >&2
                        exit 1
                        ;;
                esac
                codename=${VERSION_CODENAME:?Suite APT introuvable}
                sudo apt-get install -y ca-certificates curl
                sudo install -m 0755 -d /etc/apt/keyrings
                sudo curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
                sudo chmod a+r /etc/apt/keyrings/docker.asc
                printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
                    "$(dpkg --print-architecture)" "${ID}" "${codename}" |
                    sudo tee /etc/apt/sources.list.d/simple-app-docker.list >/dev/null
                sudo apt-get update
            fi
            # Laisser APT signaler un conflit avec une installation Docker existante.
            sudo apt-get --no-remove install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin curl
        fi
    fi
fi

if ! docker_compatible; then
    printf 'Docker doit fournir Buildx et Compose avec l’option up --wait-timeout.\n' >&2
    exit 1
fi

# Activer le moteur pour que build.sh puisse démarrer sa construction.
sudo systemctl enable --now docker
