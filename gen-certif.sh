#!/usr/bin/env bash
set -euo pipefail

# Retrouver le dossier de l'application, même depuis un autre répertoire.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$#" -ne 0 ]]; then
    printf 'Usage : bash gen-certif.sh\nAucune adresse IP ni aucun argument : le certificat est générique.\n' >&2
    exit 1
fi
if ! command -v openssl >/dev/null; then
    printf 'OpenSSL est nécessaire : relancer bash install.sh sur Ubuntu 24.04.\n' >&2
    exit 1
fi

# Ne pas écrire ou modifier les permissions d'une cible extérieure via un lien.
if [[ -L certs || -L certs/server.key || -L certs/server.crt ]]; then
    printf 'Le dossier certs et ses fichiers ne doivent pas être des liens symboliques.\n' >&2
    exit 1
fi

# Une paire existante est conservée ; une paire incomplète doit être inspectée manuellement.
if [[ -e certs/server.key || -e certs/server.crt ]]; then
    if [[ ! -f certs/server.key || ! -f certs/server.crt ]]; then
        printf 'Paire de fichiers incomplète dans %s/certs : aucun remplacement effectué.\n' "${PWD}" >&2
        exit 1
    fi
    printf 'Certificat existant conservé ; vérification en cours.\n'
fi

if [[ ! -f certs/server.key && ! -f certs/server.crt ]]; then
    # Protéger la clé dès sa création ; elle reste sans passphrase pour un futur serveur TLS.
    umask 077
    # La création exclusive du dossier bloque aussi deux générations simultanées.
    mkdir certs
    chmod 700 certs
    printf 'Création attendue : %s/certs/server.crt et %s/certs/server.key\n' "${PWD}" "${PWD}"
    # Sans SAN ni adresse : ce certificat chiffre TLS sans identifier l'adresse visitée.
    # -config /dev/null empêche une configuration OpenSSL locale d'ajouter un SAN.
    openssl req -x509 -newkey rsa:3072 -sha256 -noenc -days 30 -config /dev/null \
        -keyout certs/server.key -out certs/server.crt \
        -subj '/CN=Simple App' \
        -addext 'basicConstraints=critical,CA:FALSE' \
        -addext 'keyUsage=critical,digitalSignature,keyEncipherment' \
        -addext 'extendedKeyUsage=serverAuth'
fi

# Vérifier signature, dates et usage serveur ; une paire invalide n'est jamais remplacée.
openssl rsa -in certs/server.key -passin pass: -check -noout >/dev/null
openssl verify -check_ss_sig -purpose sslserver -CAfile certs/server.crt certs/server.crt >/dev/null
CERT_MODULUS="$(openssl x509 -in certs/server.crt -noout -modulus)"
KEY_MODULUS="$(openssl rsa -in certs/server.key -passin pass: -noout -modulus)"
if [[ "${CERT_MODULUS}" != "${KEY_MODULUS}" ]]; then
    printf 'La clé et le certificat ne correspondent pas ; aucun remplacement effectué.\n' >&2
    exit 1
fi
# Le certificat est public ; seule la clé doit rester secrète et lisible par son propriétaire.
chmod 700 certs
chmod 600 certs/server.key
chmod 644 certs/server.crt
printf 'Certificat public : %s/certs/server.crt\nClé privée : %s/certs/server.key\n' "${PWD}" "${PWD}"
openssl x509 -in certs/server.crt -noout -subject -dates -fingerprint -sha256
printf 'La génération seule n’active pas HTTPS : le serveur utilise encore sa configuration actuelle.\n'
