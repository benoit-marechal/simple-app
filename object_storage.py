import io
import os
import re
import uuid
import warnings
from functools import lru_cache
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


class ImageInvalide(ValueError):
    pass


class StockageImagesIndisponible(RuntimeError):
    pass


# Définir l'unique origine HTTPS autorisée par la CSP et le SDK ; appelée avant
# un accès S3, elle refuse une URL qui injecterait une autre source dans l'en-tête.
def origine_images():
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip()
    try:
        url = urlsplit(endpoint)
        if (url.scheme != "https" or url.path not in ("", "/") or url.query or url.fragment
                or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", url.netloc)
                or url.port is not None and not 1 <= url.port <= 65535):
            return None
    except ValueError:
        return None
    return f"https://{url.netloc}"


# Réutiliser le client du processus pour les uploads et signatures ; les secrets
# sont résolus par le SDK, sans copie dans les messages ni accès EC2 nécessaire.
@lru_cache(maxsize=1)
def client_s3():
    endpoint = origine_images()
    region = os.environ.get("S3_REGION", "").strip()
    bucket = os.environ.get("S3_BUCKET", "").strip()
    if not endpoint or not region or not bucket:
        raise StockageImagesIndisponible("Le stockage des images n'est pas configuré.")
    try:
        return boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            config=Config(
                signature_version="s3v4", s3={"addressing_style": "path"},
                connect_timeout=5, read_timeout=10, retries={"max_attempts": 2},
                request_checksum_calculation="when_required", response_checksum_validation="when_required",
            ),
        )
    except (BotoCoreError, ClientError) as erreur:
        raise StockageImagesIndisponible("Le stockage des images est indisponible.") from erreur


# Valider la pièce jointe avant tout envoi ; verify contrôle son format sans
# réencoder l'image, puis S3 reçoit exactement les octets fournis par le navigateur.
def envoyer_image(fichier):
    extension = fichier.filename.rsplit(".", 1)[-1].lower() if "." in fichier.filename else ""
    if extension not in IMAGE_EXTENSIONS:
        raise ImageInvalide("Choisir une image JPEG, PNG ou WebP.")
    contenu = fichier.stream.read(MAX_IMAGE_BYTES + 1)
    if len(contenu) > MAX_IMAGE_BYTES:
        raise ImageInvalide("L'image doit peser au maximum 5 Mio.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenu), formats=list(IMAGE_FORMATS)) as image:
                format_image = image.format
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as erreur:
        raise ImageInvalide("Le fichier n'est pas une image JPEG, PNG ou WebP valide.") from erreur
    extension, type_mime = IMAGE_FORMATS[format_image]
    cle = f"images/{uuid.uuid4().hex}.{extension}"
    try:
        client_s3().put_object(
            Bucket=os.environ["S3_BUCKET"], Key=cle, Body=contenu,
            ContentLength=len(contenu), ContentType=type_mime,
        )
    except (BotoCoreError, ClientError) as erreur:
        raise StockageImagesIndisponible("Le stockage des images est indisponible.") from erreur
    return cle


# Retirer un objet après l'échec de l'enregistrement du message ; sans ce retour
# arrière, une pièce jointe réussie resterait stockée sans message pour la retrouver.
def supprimer_image(cle):
    try:
        client_s3().delete_object(Bucket=os.environ["S3_BUCKET"], Key=cle)
    except (BotoCoreError, ClientError) as erreur:
        raise StockageImagesIndisponible("La suppression de l'image a échoué.") from erreur


# Donner au HTML un accès temporaire à une image privée ; appelée à chaque lecture,
# cette signature évite de conserver une URL expirée dans le fichier ou PostgreSQL.
def url_image(cle):
    try:
        return client_s3().generate_presigned_url(
            "get_object", Params={"Bucket": os.environ["S3_BUCKET"], "Key": cle}, ExpiresIn=3600,
        )
    except (BotoCoreError, ClientError) as erreur:
        raise StockageImagesIndisponible("La lecture des images est indisponible.") from erreur
