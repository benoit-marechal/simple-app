import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import messages


class MessagesTexteTest(unittest.TestCase):
    # Isoler chaque test dans un vrai fichier ; sans cela, il pourrait toucher les données utilisateur.
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.fichier = Path(self.dossier.name) / "messages.txt"
        self.configuration = messages.storage_mode, messages.message_file
        messages.storage_mode = "text"
        messages.message_file = str(self.fichier)
        self.horloge = patch("messages.datetime")
        self.date = self.horloge.start()
        self.date.now.return_value = datetime(2026, 11, 15, 14, 32, 8, tzinfo=ZoneInfo("Europe/Paris"))

    # Restaurer la configuration après chaque test ; sans cela, les suivants hériteraient de son état.
    def tearDown(self):
        self.horloge.stop()
        messages.storage_mode, messages.message_file = self.configuration
        self.dossier.cleanup()

    # Vérifier le format complet ; une régression pourrait supprimer les secondes ou le login.
    def test_date_secondes_login_et_message(self):
        self.assertTrue(messages.ajouter_message("Bonjour", "benoit"))
        self.assertEqual(messages.lire_messages(), [{"contenu": "15/11/2026 14:32:08 - benoit: Bonjour", "image_key": None}])
        self.assertEqual(self.date.now.call_args.args[0].key, "Europe/Paris")

    # Relire après un changement d’heure ; sans ce contrôle, une date recalculée passerait inaperçue.
    def test_date_conservee_apres_relecture(self):
        messages.ajouter_message("Message conservé", "alice")
        self.date.now.return_value = datetime(2026, 11, 16, 9, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
        self.assertEqual(messages.lire_messages(), [{"contenu": "15/11/2026 14:32:08 - alice: Message conservé", "image_key": None}])

    # Mélanger ancien et nouveau formats ; sans ce cas, une migration pourrait altérer l’historique.
    def test_ancien_message_conserve_sans_date_inventee(self):
        self.fichier.write_text("Ancien message sans métadonnées\n", encoding="utf-8")
        messages.ajouter_message("Nouveau message", "alice")
        self.assertEqual(messages.lire_messages(), [
            {"contenu": "Ancien message sans métadonnées", "image_key": None},
            {"contenu": "15/11/2026 14:32:08 - alice: Nouveau message", "image_key": None},
        ])

    # Envoyer plusieurs lignes ; sans ce contrôle, un envoi pourrait devenir plusieurs messages.
    def test_message_multiligne_reste_sur_une_ligne(self):
        messages.ajouter_message("Bonjour\r\nà tous\n!", "alice")
        self.assertEqual(messages.lire_messages(), [{"contenu": "15/11/2026 14:32:08 - alice: Bonjour à tous !", "image_key": None}])

    # Utiliser les longueurs maximales en Unicode ; sans ce cas, une troncature pourrait rester invisible.
    def test_corps_500_caracteres_et_login_40_caracteres(self):
        login = "é" * 40
        contenu = "🙂" * 500
        self.assertTrue(messages.ajouter_message(contenu, login))
        ligne = messages.lire_messages()[0]["contenu"]
        self.assertEqual(ligne, f"15/11/2026 14:32:08 - {login}: {contenu}")
        self.assertEqual(len(ligne), 564)

    # Remplir la dernière place puis dépasser la limite ; sans ce cas, un ajout excédentaire pourrait passer.
    def test_limite_du_nombre_de_messages(self):
        self.fichier.write_text("Ancien message\n" * (messages.MAX_MESSAGES - 1), encoding="utf-8")
        self.assertTrue(messages.ajouter_message("Dernière place", "alice"))
        self.assertFalse(messages.ajouter_message("En trop", "bob"))
        self.assertEqual(len(messages.lire_messages()), messages.MAX_MESSAGES)

    # Remplir exactement le fichier ; sans ce cas, le préfixe ou les octets UTF-8 pourraient être oubliés.
    def test_limite_exacte_en_octets(self):
        messages.ajouter_message("🙂", "alice")
        restant = messages.MAX_FILE_BYTES - self.fichier.stat().st_size
        self.fichier.write_text("x" * (restant - 1) + "\n", encoding="utf-8")
        self.assertTrue(messages.ajouter_message("🙂", "alice"))
        self.assertEqual(self.fichier.stat().st_size, messages.MAX_FILE_BYTES)
        self.assertFalse(messages.ajouter_message("En trop", "bob"))
        self.assertEqual(self.fichier.stat().st_size, messages.MAX_FILE_BYTES)

    # Lire un fichier surdimensionné ; sans ce cas, la limite de lecture pourrait disparaître sans alerte.
    def test_fichier_trop_volumineux_refuse_en_lecture(self):
        self.fichier.write_bytes(b"x" * (messages.MAX_FILE_BYTES + 1))
        with self.assertRaises(OSError):
            messages.lire_messages()

    # Relire les seules métadonnées de la pièce jointe ; une URL signée persistée expirerait.
    def test_reference_image_conservee_sans_url_signee(self):
        cle = "images/" + "a" * 32 + ".png"
        self.assertTrue(messages.ajouter_message("Photo", "alice", cle))
        self.assertEqual(messages.lire_messages(), [{
            "contenu": "15/11/2026 14:32:08 - alice: Photo", "image_key": cle,
        }])
        self.assertNotIn("https://", self.fichier.read_text())

    # Garder deux messages lorsqu'un ancien fichier finit sans saut de ligne ; sinon ils fusionneraient.
    def test_ancien_fichier_sans_saut_de_ligne_final(self):
        self.fichier.write_text("Ancien message", encoding="utf-8")
        messages.ajouter_message("Nouveau", "alice")
        self.assertEqual(len(messages.lire_messages()), 2)
        self.assertEqual(messages.lire_messages()[0], {"contenu": "Ancien message", "image_key": None})

    # Préserver les anciennes lignes qui ressemblent à du JSON sans être notre format de messages.
    def test_ancien_texte_json_reste_du_texte(self):
        self.fichier.write_text('{"bonjour":"monde"}\n42\n{"contenu":"bonjour"}\n', encoding="utf-8")
        self.assertEqual(messages.lire_messages(), [
            {"contenu": '{"bonjour":"monde"}', "image_key": None},
            {"contenu": "42", "image_key": None},
            {"contenu": '{"contenu":"bonjour"}', "image_key": None},
        ])

    # Refuser des métadonnées corrompues plutôt que les transmettre comme URL au template.
    def test_metadonnees_json_invalides_refusees(self):
        self.fichier.write_text('{"contenu":"Photo","image_key":123}\n', encoding="utf-8")
        with self.assertRaises(OSError):
            messages.lire_messages()


if __name__ == "__main__":
    unittest.main()
