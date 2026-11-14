import fcntl
import os

import psycopg

storage_mode = os.environ.get("STORAGE_MODE", "text")
if storage_mode not in {"text", "postgres"}:
    raise ValueError("STORAGE_MODE doit valoir text ou postgres.")
message_file = os.environ.get("MESSAGE_FILE", "/data/messages.txt")
MAX_MESSAGES = 1000
MAX_FILE_BYTES = 1024 * 1024


# Relier le stockage SQL aux routes : appelée seulement en mode postgres ;
# sans elle, chaque opération devrait répéter les paramètres de connexion.
def connexion_postgres():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "db"),
        dbname=os.environ.get("DB_NAME", "simple_app"),
        user=os.environ.get("DB_USER", "simple_app"),
        password=os.environ.get("DB_PASSWORD", "simple_app_demo"),
        connect_timeout=5,
    )


# Fournir une liste bornée à la page et au contrôle de santé ; sans cette limite,
# un fichier ou une table trop volumineux pourrait saturer la mémoire du web.
def lire_messages():
    if storage_mode == "text":
        try:
            with open(message_file, encoding="utf-8") as fichier:
                fcntl.flock(fichier, fcntl.LOCK_SH)
                if os.path.getsize(message_file) > MAX_FILE_BYTES:
                    raise OSError("Le fichier de messages dépasse sa limite.")
                messages = fichier.read().splitlines()
                return messages[:MAX_MESSAGES]
        except FileNotFoundError:
            return []
    with connexion_postgres() as connexion:
        with connexion.cursor() as curseur:
            curseur.execute("SELECT contenu FROM messages ORDER BY id LIMIT %s", (MAX_MESSAGES,))
            messages = []
            for ligne in curseur.fetchall():
                messages.append(ligne[0])
            return messages


# Enregistrer un ajout après validation du formulaire : appelée par POST / ;
# le verrou empêche deux requêtes de dépasser ensemble la capacité autorisée.
def ajouter_message(contenu):
    if storage_mode == "text":
        contenu = " ".join(contenu.splitlines())
        with open(message_file, "a+", encoding="utf-8") as fichier:
            fcntl.flock(fichier, fcntl.LOCK_EX)
            taille = os.path.getsize(message_file)
            if taille + len((contenu + "\n").encode("utf-8")) > MAX_FILE_BYTES:
                return False
            fichier.seek(0)
            if len(fichier.read().splitlines()) >= MAX_MESSAGES:
                return False
            fichier.write(contenu + "\n")
        return True
    with connexion_postgres() as connexion:
        with connexion.cursor() as curseur:
            curseur.execute("LOCK TABLE messages IN EXCLUSIVE MODE")
            curseur.execute("SELECT count(*) FROM messages")
            if curseur.fetchone()[0] >= MAX_MESSAGES:
                return False
            curseur.execute("INSERT INTO messages (contenu) VALUES (%s)", (contenu,))
    return True
