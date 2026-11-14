from cachelib import FileSystemCache
from cachelib.serializers import JSONSerializer


# Utiliser du JSON pour les sessions sur disque : sans ce choix,
# CacheLib utiliserait pickle, inadapté à des fichiers qui seront partagés par NFS.
class SessionFileCache(FileSystemCache):
    serializer = JSONSerializer()
