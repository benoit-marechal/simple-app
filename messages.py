import fcntl
import os
from datetime import datetime
from zoneinfo import ZoneInfo

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


# Dater et attribuer un ajout validé par POST /, puis le conserver une seule fois ;
# sans ce préfixe, la lecture perdrait l'heure et le login de son auteur.
# Les verrous libérés à la fermeture/fin de transaction bornent les ajouts simultanés.
def ajouter_message(contenu, login):
    date_heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M:%S")
    contenu = " ".join(contenu.splitlines())
    contenu = f"{date_heure} - {login}: {contenu}"
    if storage_mode == "text":
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
