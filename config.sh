# Choisir text pour un fichier sur cette instance, ou postgres pour PostgreSQL.
STORAGE_MODE=text

# memory perd les connexions au redémarrage ; file les conserve sur cette instance.
SESSION_STORAGE=memory

# Sur une VM distante : 0.0.0.0 et ajouter son IP publique dans APP_HOSTS.
# Le groupe de sécurité doit limiter TCP 8080 aux sources du TP.
APP_BIND=127.0.0.1
APP_HOSTS=localhost,127.0.0.1
