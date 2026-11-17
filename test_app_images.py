import io
import os
import tempfile
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
            "IMAGE_STORAGE": "s3",
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

    # Placer la saisie avant le fil et inverser seulement l'affichage ; sans ce cas,
    # les nouveaux messages pourraient revenir sous l'historique après une modification du template.
    def test_formulaire_en_haut_et_messages_recents_en_premier(self):
        self.lecture.return_value = [
            {"contenu": "Ancien message", "image_key": None},
            {"contenu": "Message intermédiaire", "image_key": None},
            {"contenu": "Dernier message", "image_key": None},
        ]
        body = self.client.get("/").get_data(as_text=True)
        self.assertLess(body.index('id="contenu"'), body.index('aria-label="Messages"'))
        self.assertLess(body.index("Dernier message"), body.index("Message intermédiaire"))
        self.assertLess(body.index("Message intermédiaire"), body.index("Ancien message"))

    # Un texte sans pièce jointe doit rester un simple texte ; sans ce contrôle,
    # un emplacement d'image vide ou un message d'erreur pourrait apparaître à chaque ligne.
    def test_message_sans_image_sans_emplacement_reserve(self):
        self.lecture.return_value = [{"contenu": "Texte seul", "image_key": None}]
        body = self.client.get("/").get_data(as_text=True)
        item = body.split("<li>", 1)[1].split("</li>", 1)[0]
        self.assertIn("Texte seul", item)
        self.assertNotIn("<img", item)
        self.assertNotIn("image-message", item)
        self.assertNotIn("image-indisponible", item)
        self.sdk.generate_presigned_url.assert_not_called()

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


class ImagesLocalesFormulaireTest(unittest.TestCase):
    # Exécuter le formulaire et la lecture de fichiers réels sans cloud ni stockage de messages persistant.
    def setUp(self):
        application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        application.limiter.enabled = False
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "images"
        self.environ = patch.dict(os.environ, {
            "IMAGE_STORAGE": "local", "IMAGE_DIRECTORY": str(self.directory),
        })
        self.environ.start()
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["login"] = "alice"
        self.ecriture_patch = patch("app.ajouter_message", return_value=True)
        self.ecriture = self.ecriture_patch.start()
        self.lecture_patch = patch("app.lire_messages", return_value=[])
        self.lecture = self.lecture_patch.start()
        self.sdk_patch = patch("object_storage.client_s3", side_effect=AssertionError("Aucun accès S3 attendu"))
        self.sdk_patch.start()

    # Nettoyer les données et les remplacements afin que chaque cas teste son propre état.
    def tearDown(self):
        self.sdk_patch.stop()
        self.lecture_patch.stop()
        self.ecriture_patch.stop()
        self.environ.stop()
        self.temporary.cleanup()

    # Lier une image à un message, l'afficher depuis la même origine, puis en servir les octets originaux.
    def test_envoi_affichage_et_lecture_authentifiee(self):
        original = image_png()
        response = self.client.post("/", data={"contenu": "Photo locale", "image": (io.BytesIO(original), "photo.png")})
        self.assertEqual(response.status_code, 303)
        cle = self.ecriture.call_args.args[2]
        self.lecture.return_value = [{"contenu": "Photo locale", "image_key": cle}]
        page = self.client.get("/")
        self.assertIn(f'src="/{cle}"', page.get_data(as_text=True))
        self.assertIn("img-src 'self';", page.headers["Content-Security-Policy"])
        response = self.client.get("/" + cle)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, original)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        response.close()
        anonymous = application.app.test_client()
        self.assertEqual(anonymous.get("/" + cle).status_code, 303)

    # Annuler un upload après un refus ou une panne d'écriture du message, sans laisser de fichier orphelin.
    def test_rollback_local_apres_refus_et_erreur_message(self):
        for resultat, erreur, statut in ((False, None, 409), (None, OSError("Disque indisponible"), 503)):
            with self.subTest(statut=statut):
                self.ecriture.return_value = resultat
                self.ecriture.side_effect = erreur
                response = self.client.post("/", data={"contenu": "Photo", "image": (io.BytesIO(image_png()), "photo.png")})
                self.assertEqual(response.status_code, statut)
                self.assertEqual(list(self.directory.iterdir()), [])

    # Garder les messages sans image sans emplacement réservé et refuser les chemins de lecture libres.
    def test_texte_seul_et_chemins_refuses(self):
        self.assertEqual(self.client.post("/", data={"contenu": "Texte seul"}).status_code, 303)
        self.ecriture.assert_called_once_with("Texte seul", "alice", None)
        self.lecture.return_value = [{"contenu": "Texte seul", "image_key": None}]
        item = self.client.get("/").get_data(as_text=True).split("<li>", 1)[1].split("</li>", 1)[0]
        self.assertNotIn("<img", item)
        for url in ("/images/..", "/images/..%2Fsecret.txt", "/images/password.txt"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.directory.mkdir()
        outside = Path(self.temporary.name) / "outside.png"
        outside.write_bytes(b"prive")
        name = "a" * 32 + ".png"
        (self.directory / name).symlink_to(outside)
        self.assertEqual(self.client.get("/images/" + name).status_code, 404)

    # Le stockage local ne doit pas ouvrir la route d'image lorsque S3 est choisi.
    def test_route_locale_absente_en_mode_s3(self):
        with patch.dict(os.environ, {"IMAGE_STORAGE": "s3"}):
            self.assertEqual(self.client.get("/images/" + "a" * 32 + ".png").status_code, 404)

    # Distinguer un fichier absent d'une panne disque ; sans cette distinction,
    # une ancienne référence ferait annoncer à tort une indisponibilité du service.
    def test_image_absente_404_et_panne_disque_503(self):
        url = "/images/" + "a" * 32 + ".png"
        self.assertEqual(self.client.get(url).status_code, 404)
        with patch("app.send_file", side_effect=PermissionError("Accès refusé")):
            self.assertEqual(self.client.get(url).status_code, 503)

    # Une panne du disque d'images doit laisser les textes lisibles, sans donner un lien cassé au navigateur.
    def test_panne_lecture_images_conserve_les_textes(self):
        self.lecture.return_value = [{"contenu": "Message lisible", "image_key": "images/" + "a" * 32 + ".png"}]
        with patch("object_storage.chemin_image", side_effect=PermissionError("Accès refusé")):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Message lisible", response.get_data(as_text=True))
        self.assertIn("Image temporairement indisponible", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
