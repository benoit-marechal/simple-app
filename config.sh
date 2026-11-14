# Choisir text pour un fichier sur cette instance, ou postgres pour PostgreSQL.
STORAGE_MODE=text

# memory perd les connexions au redémarrage ; file les conserve sur cette instance.
SESSION_STORAGE=memory

# Utiliser true uniquement lorsque le navigateur accède à l’application en HTTPS.
SESSION_COOKIE_SECURE=false

# Accès local par défaut ; 0.0.0.0 publie sur les interfaces de la VM.
APP_BIND=127.0.0.1
APP_HOSTS=localhost,127.0.0.1
