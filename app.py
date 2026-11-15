import os
from datetime import timedelta
from pathlib import Path

import psycopg
from cachelib import SimpleCache
from flask import Flask, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash

from messages import ajouter_message, lire_messages
from session_files import SessionFileCache

app = Flask(__name__)
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
    MAX_CONTENT_LENGTH=16384,
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
    reponse.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
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


# Conserver et afficher les messages : appelée sur GET/POST / ; sans elle,
# un utilisateur connecté ne pourrait ni enregistrer un texte ni consulter la liste.
@app.route("/", methods=["GET", "POST"])
@limiter.limit("60 per minute", methods=["POST"])
def index():
    if "login" not in session:
        return redirect(url_for("login"), code=303)
    if request.method == "POST":
        contenu = request.form.get("contenu", "").strip()
        if not 1 <= len(contenu) <= 500:
            return "Le message doit contenir de 1 à 500 caractères.", 400
        if not ajouter_message(contenu, session["login"]):
            return "La liste des messages est pleine.", 409
        return redirect(url_for("index"), code=303)
    return render_template("index.html", messages=lire_messages(), instance_hostname=instance_hostname)


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
