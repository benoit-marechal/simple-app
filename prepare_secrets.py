import os
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash

credentials = Path("/credentials")
credentials.mkdir(mode=0o700, parents=True, exist_ok=True)
if credentials.is_symlink():
    raise SystemExit("Le répertoire des identifiants ne doit pas être un lien symbolique.")
os.chown(credentials, 1000, 1000)
os.chmod(credentials, 0o700)

key_file = credentials / "secret.key"
hash_file = credentials / "password.hash"
password_file = credentials / "password.txt"
files = (key_file, hash_file, password_file)
present = [path.exists() for path in files]

if any(present) and not all(present):
    raise SystemExit("Identifiants incomplets : aucun fichier existant n’a été remplacé.")

if all(present):
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise SystemExit("Un fichier d’identifiants existant est invalide.")
        os.chown(path, 1000, 1000)
        os.chmod(path, 0o600)
else:
    secret_key = os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32)
    password = os.environ.get("APP_PASSWORD") or secrets.token_urlsafe(18)
    if len(password) < 12:
        raise SystemExit("APP_PASSWORD doit contenir au moins 12 caractères.")
    if len(secret_key) < 32:
        raise SystemExit("APP_SECRET_KEY doit contenir au moins 32 caractères.")
    password_hash = generate_password_hash(password, method="scrypt")
    # La création exclusive conserve les identifiants déjà présents, même en cas de relance.
    for path, value in ((key_file, secret_key), (hash_file, password_hash), (password_file, password)):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(value)
        os.chown(path, 1000, 1000)
