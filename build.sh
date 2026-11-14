#!/usr/bin/env bash
set -euo pipefail

# Construire avec les sources voisines du script, même lors d'un appel par cloud-init.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sudo docker compose build
# Attendu : l'image web est construite ; les conteneurs et les données restent en place.
