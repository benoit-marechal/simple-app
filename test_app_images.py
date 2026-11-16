import io
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import EndpointConnectionError
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from test_object_storage import image_png
from object_storage import StockageImagesIndisponible

read_text = Path.read_text
password_hash = generate_password_hash("mot-de-passe-de-test")


# Fournir des secrets fictifs seulement au chargement de Flask ; aucun test ne doit
# lire ni remplacer les fichiers d'authentification de la machine qui l'exécute.
def lire_secret_test(path, *args, **kwargs):
    if str(path) == "/run/secrets/secret_key":
        return "cle-de-session-de-test-uniquement-1234567890"
    if str(path) == "/run/secrets/password_hash":
        return password_hash
    return read_text(path, *args, **kwargs)


with patch.object(Path, "read_text", lire_secret_test), patch.dict(os.environ, {"SESSION_STORAGE": "memory"}):
    import app as application


class ImagesFormulaireTest(unittest.TestCase):
    # Simuler seulement le fournisseur et le stockage des messages ; le vrai formulaire,
    # le parseur multipart et la validation Pillow restent exécutés pendant les tests.
    def setUp(self):
        application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        application.limiter.enabled = False
        self.environ = patch.dict(os.environ, {
            "S3_ENDPOINT_URL": "https://s3.example.com", "S3_REGION": "gra", "S3_BUCKET": "test-images",
        })
        self.environ.start()
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["login"] = "alice"
        self.sdk = Mock()
        self.sdk.generate_presigned_url.return_value = "https://s3.example.com/test-images/images/photo.png?signature=test"
        self.s3_patch = patch("object_storage.client_s3", return_value=self.sdk)
        self.s3_patch.start()
        self.ecriture_patch = patch("app.ajouter_message", return_value=True)
        self.ecriture = self.ecriture_patch.start()
        self.lecture_patch = patch("app.lire_messages", return_value=[])
        self.lecture = self.lecture_patch.start()

    # Restaurer les fonctions et paramètres partagés ; sinon les tests suivants hériteraient des pannes simulées.
    def tearDown(self):
        self.lecture_patch.stop()
        self.ecriture_patch.stop()
        self.s3_patch.stop()
        self.environ.stop()

    # Conserver l'usage texte existant ; un message sans pièce jointe ne dépend pas de S3.
    def test_texte_seul_sans_appel_s3(self):
        with patch.dict(os.environ, {"S3_ENDPOINT_URL": "", "S3_REGION": "", "S3_BUCKET": ""}):
            response = self.client.post("/", data={"contenu": "Bonjour"})
        self.assertEqual(response.status_code, 303)
        self.ecriture.assert_called_once_with("Bonjour", "alice", None)
        self.sdk.put_object.assert_not_called()

    # Relier un envoi valide au message, sans conserver une URL signée ni changer le fichier original.
    def test_image_liee_au_message(self):
        original = image_png()
        response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(original), "photo.png")})
        self.assertEqual(response.status_code, 303)
        cle = self.sdk.put_object.call_args.kwargs["Key"]
        self.ecriture.assert_called_once_with("Photo", "alice", cle)
        self.assertEqual(self.sdk.put_object.call_args.kwargs["Body"], original)

    # Garder une seule pièce jointe ; sinon plusieurs fichiers seraient silencieusement ignorés.
    def test_deux_images_refusees(self):
        data = MultiDict([
            ("contenu", "Photo"), ("image", (io.BytesIO(image_png()), "a.png")),
            ("image", (io.BytesIO(image_png()), "b.png")),
        ])
        self.assertEqual(self.client.post("/", data=data).status_code, 400)
        self.ecriture.assert_not_called()
        self.sdk.put_object.assert_not_called()

    # Ne pas publier un message dont la pièce jointe a échoué ; la référence serait cassée dès l'enregistrement.
    def test_panne_upload_aucun_message(self):
        self.sdk.put_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.example.com")
        response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
        self.assertEqual(response.status_code, 503)
        self.ecriture.assert_not_called()

    # Un fournisseur absent doit produire une erreur contrôlée tout en conservant l'usage texte.
    def test_stockage_non_configure_aucun_message_image(self):
        with patch("object_storage.client_s3", side_effect=StockageImagesIndisponible("Non configuré")):
            response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
        self.assertEqual(response.status_code, 503)
        self.ecriture.assert_not_called()

    # Nettoyer l'objet lorsque la liste est pleine ; une écriture S3 réussie ne garantit pas l'ajout du message.
    def test_liste_pleine_supprime_image_orpheline(self):
        self.ecriture.return_value = False
        response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
        self.assertEqual(response.status_code, 409)
        cle = self.sdk.put_object.call_args.kwargs["Key"]
        self.sdk.delete_object.assert_called_once_with(Bucket="test-images", Key=cle)

    # Garder l'erreur du stockage principal même si le nettoyage échoue ; sinon une panne masquerait l'autre.
    def test_erreur_message_et_nettoyage_sans_masquer_erreur_initiale(self):
        self.ecriture.side_effect = OSError("Erreur disque simulée")
        self.sdk.delete_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.example.com")
        response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
        self.assertEqual(response.status_code, 503)
        self.assertIn("Stockage temporairement indisponible", response.get_data(as_text=True))
        self.sdk.delete_object.assert_called_once()

    # Afficher une pièce jointe par une balise passive ; sans la CSP correcte le navigateur la bloquerait.
    def test_affichage_html_et_csp(self):
        self.lecture.return_value = [{"contenu": "Message <script>", "image_key": "images/photo.png"}]
        response = self.client.get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('enctype="multipart/form-data"', body)
        self.assertIn('class="image-message" src="https://s3.example.com/', body)
        self.assertIn('loading="lazy"', body)
        self.assertIn("Message &lt;script&gt;", body)
        self.assertIn("img-src https://s3.example.com;", response.headers["Content-Security-Policy"])
        self.assertIn("script-src 'none'", response.headers["Content-Security-Policy"])

    # Une panne de signature ne doit pas empêcher la lecture des textes ni boucler sur chaque image.
    def test_images_indisponibles_textes_lisibles(self):
        self.lecture.return_value = [
            {"contenu": "Premier message", "image_key": "images/a.png"},
            {"contenu": "Second message", "image_key": "images/b.png"},
        ]
        self.sdk.generate_presigned_url.side_effect = EndpointConnectionError(endpoint_url="https://s3.example.com")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Premier message", response.get_data(as_text=True))
        self.assertIn("Second message", response.get_data(as_text=True))
        self.assertEqual(self.sdk.generate_presigned_url.call_count, 1)

    # Refuser le multipart avant lecture d'un corps trop grand ; la limite d'image seule ne suffit pas.
    def test_requete_trop_volumineuse(self):
        response = self.client.post(
            "/", data=b"x" * (6 * 1024 * 1024 + 1),
            content_type="multipart/form-data; boundary=test",
        )
        self.assertEqual(response.status_code, 413)
        self.ecriture.assert_not_called()
        self.sdk.put_object.assert_not_called()

    # CSRF reste requis avec un fichier ; sans ce cas, une nouvelle route d'upload pourrait contourner la protection.
    def test_upload_sans_csrf_refuse(self):
        application.app.config["WTF_CSRF_ENABLED"] = True
        response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
        self.assertEqual(response.status_code, 400)
        self.ecriture.assert_not_called()
        self.sdk.put_object.assert_not_called()

    # Le répartiteur doit contrôler les messages sans signer des images ni joindre S3 à chaque sonde.
    def test_health_sans_s3(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.sdk.put_object.assert_not_called()
        self.sdk.generate_presigned_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
