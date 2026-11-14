# Choisir text pour un fichier sur cette instance, ou postgres pour PostgreSQL.
STORAGE_MODE=text

# memory perd les connexions au redémarrage ; file les conserve sur cette instance.
SESSION_STORAGE=memory

# Sur une VM distante : 0.0.0.0 publie le backend sur les interfaces de la VM.
# Le groupe de sécurité doit limiter TCP 8080 aux sources autorisées.
APP_BIND=127.0.0.1

# Facultatif : laisser vide pour accepter toutes les adresses d'accès.
APP_HOSTS=
