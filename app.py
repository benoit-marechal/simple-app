import os
from datetime import timedelta
from pathlib import Path

import psycopg
from cachelib import SimpleCache
from flask import Flask, abort, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge

from messages import ajouter_message, lire_messages
from object_storage import (
    ImageInvalide, StockageImagesIndisponible, chemin_image, envoyer_image, mode_images, origine_images,
    supprimer_image, url_image,
)
from session_files import SessionFileCache

app = Flask(__name__)
mode_images()
secret_key = Path("/run/secrets/secret_key").read_text().strip()
password_hash = Path("/run/secrets/password_hash").read_text().strip()
if len(secret_key) < 32 or not password_hash.startswith("scrypt:"):
    raise RuntimeError("Les fichiers de secrets doivent contenir une clé et un hash scrypt valides.")

session_storage = os.environ.get("SESSION_STORAGE", "memory")
if session_storage == "memory":
    session_cache = SimpleCache(threshold=1000, default_timeout=7200)
elif session_storage == "file":
    session_cache = SessionFileCache("/sessions", threshold=1000, default_timeout=7200, mode=0o600)
else:
    raise ValueError("SESSION_STORAGE doit valoir memory ou file.")

# Une liste d'hôtes peut restreindre les adresses d'accès.
allowed_hosts = os.environ.get("APP_HOSTS", "").strip()
app.config.update(
    SECRET_KEY=secret_key,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    TRUSTED_HOSTS=allowed_hosts.split(",") if allowed_hosts else None,
    SESSION_TYPE="cachelib",
    SESSION_CACHELIB=session_cache,
    SESSION_COOKIE_NAME="simple_app_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    SESSION_REFRESH_EACH_REQUEST=False,
)
Session(app)
CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])
instance_hostname = os.environ.get("INSTANCE_HOSTNAME", "non renseignée")


# Protéger les pages et les cookies : appelé après chaque réponse ; sans lui,
# le navigateur pourrait réutiliser une page privée ou accepter des contenus actifs.
@app.after_request
def proteger_reponse(reponse):
    source_images = origine_images() or "'none'"
    reponse.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
        f"img-src {source_images}; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


# Authentifier l'utilisateur : appelée sur GET/POST /login ; sans elle,
# aucun contrôle du mot de passe commun ni renouvellement de session ne serait réalisé.
@app.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: "60 per minute" if request.method == "POST" else "120 per minute", per_method=True)
def login():
    erreur = None
    statut = 200
    if request.method == "POST":
        nom = request.form.get("login", "").strip()
        if not 1 <= len(nom) <= 40 or not nom.isprintable():
            erreur, statut = "Le login doit contenir de 1 à 40 caractères.", 400
        elif not check_password_hash(password_hash, request.form.get("password", "")):
            app.logger.warning("Connexion refusée : mot de passe incorrect.")
            erreur, statut = "Connexion refusée.", 401
        else:
            session.clear()
            session["login"] = nom
            session.permanent = True
            app.session_interface.regenerate(session)
            return redirect(url_for("index"), code=303)
    return render_template("login.html", erreur=erreur, instance_hostname=instance_hostname), statut


# Nettoyer la pièce jointe après un refus ou une erreur du stockage des messages ;
# une panne du nettoyage est signalée sans masquer l'erreur initiale du formulaire.
def nettoyer_image_orpheline(cle):
    if cle:
        try:
            supprimer_image(cle)
        except StockageImagesIndisponible:
            app.logger.warning("Une image sans message n'a pas pu être supprimée du stockage.")


# Conserver texte et référence d'image après un POST validé, puis afficher les messages ;
# sans cette route, l'image ne serait pas reliée à son auteur et à sa date.
@app.route("/", methods=["GET", "POST"])
@limiter.limit("60 per minute", methods=["POST"])
def index():
    if "login" not in session:
        return redirect(url_for("login"), code=303)
    if request.method == "POST":
        contenu = request.form.get("contenu", "").strip()
        if not 1 <= len(contenu) <= 500:
            return "Le message doit contenir de 1 à 500 caractères.", 400
        images = request.files.getlist("image")
        if len(images) > 1:
            return "Joindre une seule image par message.", 400
        cle = envoyer_image(images[0]) if images and images[0].filename else None
        try:
            ajoute = ajouter_message(contenu, session["login"], cle)
        except Exception:
            nettoyer_image_orpheline(cle)
            raise
        if not ajoute:
            nettoyer_image_orpheline(cle)
            return "La liste des messages est pleine.", 409
        return redirect(url_for("index"), code=303)
    messages = lire_messages()
    images_indisponibles = False
    for message in messages:
        message["image_url"] = None
        if message["image_key"] and not images_indisponibles:
            try:
                message["image_url"] = url_image(message["image_key"])
            except StockageImagesIndisponible:
                images_indisponibles = True
                app.logger.warning("Les images sont indisponibles ; les messages restent lisibles.")
    return render_template("index.html", messages=messages, instance_hostname=instance_hostname)


# Servir un original local uniquement après connexion ; sans ce contrôle,
# une URL d'image pourrait donner accès aux fichiers hors de la session privée.
@app.get("/images/<filename>")
def image_locale(filename):
    if "login" not in session:
        return redirect(url_for("login"), code=303)
    if mode_images() != "local":
        abort(404)
    try:
        chemin = chemin_image(f"images/{filename}")
    except ImageInvalide:
        abort(404)
    try:
        return send_file(chemin)
    except FileNotFoundError:
        abort(404)


# Fermer l'accès de l'utilisateur : appelée uniquement sur POST /logout ; sans elle,
# la session resterait utilisable après son départ.
@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"), code=303)


# Signaler la disponibilité du stockage : appelée par GET /health sans connexion ;
# sans elle, le répartiteur ne distinguerait pas un frontal incapable de lire les messages.
@app.get("/health")
@limiter.exempt
def health():
    lire_messages()
    return "ok", 200


# Masquer les détails internes : appelée lors d'une panne disque ou PostgreSQL ;
# sans elle, les réponses pourraient divulguer des détails au lieu d'un état indisponible.
@app.errorhandler(OSError)
@app.errorhandler(psycopg.Error)
def stockage_indisponible(erreur):
    app.logger.error("Le stockage des messages est indisponible.")
    return "Stockage temporairement indisponible.", 503


# Expliquer un refus de formulaire : appelée si le jeton CSRF manque ou expire ;
# sans elle, l'utilisateur recevrait le message technique par défaut de Flask-WTF.
@app.errorhandler(CSRFError)
def formulaire_refuse(erreur):
    return "Formulaire expiré ou invalide. Recharge la page.", 400


# Expliquer le refus avant tout ajout de message ; sans ces réponses contrôlées,
# un fichier invalide ou une panne de stockage produirait une erreur interne peu utile.
@app.errorhandler(ImageInvalide)
def image_refusee(erreur):
    return str(erreur), 400


# Garder les détails du fournisseur et des clés hors des réponses HTTP ; appelée
# si l'envoi échoue, cette réponse laisse l'utilisateur réessayer son message.
@app.errorhandler(StockageImagesIndisponible)
def images_indisponibles(erreur):
    app.logger.warning("Le stockage des images est indisponible.")
    return "Stockage des images temporairement indisponible. Le message n'a pas été ajouté.", 503


# Borner le corps HTTP complet, en plus des 5 Mio par image ; sans ce contrôle,
# les champs multipart pourraient contourner la limite de la pièce jointe.
@app.errorhandler(RequestEntityTooLarge)
def envoi_trop_volumineux(erreur):
    return "L'envoi dépasse 6 Mio ; choisir une image de 5 Mio maximum.", 413
