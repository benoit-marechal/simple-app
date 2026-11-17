# Choisir text pour un fichier sur cette instance, ou postgres pour PostgreSQL.
STORAGE_MODE=text

# local conserve les originaux dans /data/images ; s3 utilise le service configuré.
IMAGE_STORAGE=local

# memory perd les connexions au redémarrage ; file les conserve sur cette instance.
SESSION_STORAGE=memory

# Sur une VM distante : 0.0.0.0 publie le backend sur les interfaces de la VM.
# Le groupe de sécurité doit limiter TCP 8080 aux sources autorisées.
APP_BIND=127.0.0.1

# Facultatif : laisser vide pour accepter toutes les adresses d'accès.
APP_HOSTS=

# En mode s3, /etc/simple-app/s3.yml est conservé hors du clone.
# Les clés restent dans un fichier privé monté en lecture seule, pas dans config.sh.
