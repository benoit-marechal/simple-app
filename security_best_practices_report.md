# Revue de sécurité OWASP

La version initiale ne devait pas être exposée directement sur Internet : lecture et ajout anonymes, stockage sans plafond et absence de TLS fourni. La version revue ajoute l’authentification demandée, les sessions serveur, les contrôles des formulaires et des limites de ressources. Elle écoute seulement sur `127.0.0.1` par défaut.

**L’exposition Internet n’est pas validée.** Le cookie de session est désormais imposé avec l’attribut `Secure` dans le code : une session navigateur nécessite HTTPS. Un certificat autosigné générique est généré séparément ; sa création ne met pas en place la terminaison TLS. Le filtrage OVHcloud et le comportement du répartiteur n’ont pas été vérifiés. Le mot de passe commun protège l’accès au lab ; un login libre ne prouve pas l’identité d’un étudiant.

## Périmètre et preuves

- Contrôle local du 14 novembre 2026 : Python 3.12, Flask, templates HTML, scripts, Dockerfile, Compose, stockage texte et sessions mémoire/fichier.
- Référentiel : [OWASP Top 10:2025](https://top10.owasp.org/2025/) et [considérations de sécurité Flask](https://flask.palletsprojects.com/en/stable/web-security/).
- Tests HTTP locaux et clients Flask isolés ; aucun scan de VM, test de saturation ou test du réseau OVHcloud.
- Image examinée lors du contrôle précédent : `sha256:6a837ae16ec16fe602d3a9bd2c9dd8f6c186bc7d7cc4f447b889ad475495a60e`, Linux ARM64. Les résultats de dépendances ci-dessous concernent cette image ; ils ne valident pas une image reconstruite après les changements du cookie et du certificat.
- Aucun mot de passe, clé de signature ou cookie n’est inclus dans ce rapport ou dans l’image. Les répertoires de secrets et de données n’ont pas été transmis à un service d’analyse. Les outils ont téléchargé leurs bases publiques ; pip-audit a interrogé les avis à partir des noms et versions de paquets.

## 1. Accès anonyme aux messages — élevé, corrigé localement

- **OWASP :** A01 contrôle d’accès, A07 authentification.
- **Preuve initiale :** GET `/` répondait 200 et POST `/` 303 sans connexion. Un visiteur pouvait lire ou ajouter des messages.
- **Correction :** [app.py](app.py:67) impose le mot de passe commun et un login de 1 à 40 caractères ; [la route des messages](app.py:93) exige une session. Le hash scrypt et la clé sont lus depuis des fichiers montés en lecture seule, jamais depuis le dépôt.
- **Vérification :** accès anonyme redirigé ; mauvais mot de passe refusé ; identifiant de session renouvelé après connexion ; bouton de déconnexion en POST ; ancien cookie refusé après déconnexion.
- **Limite :** tous les participants connaissent le même mot de passe et disposent des mêmes droits. Ce modèle ne permet pas une attribution fiable à une personne réelle.

## 2. Épuisement du stockage et de la mémoire — élevé, protections applicatives ajoutées

- **OWASP :** A06 conception, A02 configuration.
- **Preuve initiale :** le client de test a pu rendre 1001 messages puis en ajouter un autre. Le code relisait toute la liste sans plafond.
- **Correction :** [messages.py](messages.py:10) borne le fichier à 1 Mio et la liste à 1000 messages. Les écritures texte sont verrouillées ; le comptage et l’insertion SQL sont sérialisés dans une transaction. Les messages restent limités à 500 caractères et les requêtes à 16 Kio.
- **Débit :** 60 tentatives de connexion POST par minute et par IP, 120 ouvertures de la page de connexion, 60 ajouts par minute. Ces limites en mémoire s’appliquent par instance ; elles ne constituent pas une protection DDoS globale. Une classe derrière une même IP partage ces limites.
- **Vérification :** ajouts refusés en 409 lorsque le fichier ou le nombre de messages atteint sa limite ; corps trop gros refusé en 413 ; 61e tentative de connexion refusée en 429 dans un client de test isolé.
- **Reste :** le frontal Internet doit aussi borner les connexions lentes et le débit. Gunicorn doit être protégé par une entrée HTTP adaptée ; [sa documentation](https://gunicorn.org/deploy/) explique notamment le besoin de traiter les clients lents en amont.

## 3. Formulaires et sessions — moyen à élevé selon le contrôle, corrigé localement

- **OWASP :** A01, A07, A08 intégrité.
- **Preuve initiale :** un POST avec une origine externe était accepté. Aucune session authentifiée n’existait alors : ce constat ne prouvait pas, à lui seul, un détournement de privilèges par CSRF.
- **Correction :** Flask-WTF protège les POST de connexion, d’ajout et de déconnexion. Le cookie contient un identifiant opaque ; les données de session restent sur le serveur. Cookie `HttpOnly`, `SameSite=Lax`, durée de deux heures et attribut `Secure` imposé dans le code. Aucune option de `config.sh`, de Compose ou d’environnement ne désactive cet attribut.
- **Stockage :** mémoire par défaut, ou fichiers via CacheLib et son sérialiseur JSON dans [session_files.py](session_files.py:1). Le mode fichier n’utilise pas le sérialiseur pickle par défaut de CacheLib.
- **Vérifications :** les essais précédents ont confirmé le refus sans jeton CSRF, la perte des sessions mémoire après redémarrage, la conservation des sessions fichier et le refus du cookie de l’instance A par une instance B disposant d’un autre disque de sessions. Le contrôle ciblé actuel confirme `SESSION_COOKIE_SECURE=True` même si une variable d’environnement tente de le désactiver. Ces essais ne constituent pas une recette navigateur de l’accès HTTPS.
- **Reste :** les sessions fichier sont locales. NFS sera une étape séparée, avec même répertoire de sessions, mêmes droits UID/GID et même clé de signature. Le répertoire devra être réservé au cache des sessions et accessible seulement aux hôtes autorisés.
- **Référence :** [prévention CSRF OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## 4. HTTPS et exposition réseau — élevé si publication HTTP, non validé sur Internet

- **OWASP :** A04 cryptographie, A02 configuration.
- **Transport :** l’attribut `Secure` empêche l’envoi du cookie de session sur un accès HTTP distant. Il ne chiffre pas lui-même le transport et ne transforme pas un service HTTP en HTTPS. Sans terminaison TLS, la connexion du navigateur ne peut pas conserver sa session et un mot de passe saisi en HTTP reste exposé.
- **Certificat :** `gen-certif.sh` crée sans saisie ni argument un certificat autosigné générique `CN=Simple App`, RSA 3072 bits, SHA-256 et 30 jours de validité, sans extension SAN ni adresse IP. Une paire existante valide est conservée. Une paire incomplète, invalide ou expirée est refusée sans écrasement ; la clé privée reste hors du dépôt et du contexte Docker. Le backend reste HTTP sur TCP 8080 ; l’administrateur raccorde séparément HTTPS.
- **Identité TLS :** le navigateur signale la confiance absente dans l’émetteur autosigné et la non-correspondance du nom générique avec l’adresse IP. L’empreinte SHA-256 doit être comparée avec celle relevée sur la VM par SSH avant une exception. Une exception de confiance ne corrige pas la correspondance du nom ; ce certificat de TP ne fournit pas une identité serveur validée pour un usage réel.
- **Réseau :** [Compose](docker-compose.yml:6) publie uniquement sur la boucle locale par défaut. `APP_HOSTS=` est vide par défaut : le filtrage de l’en-tête HTTP Host est facultatif et aucune IP n’est à saisir pour déployer le TP. Une liste non vide active ce contrôle et doit inclure les adresses d’accès et celles des contrôles de santé. Le groupe de sécurité ou le frontal doit limiter l’accès selon le TP ; cette option ne remplace pas le filtrage réseau. Les contrôles d’authentification, CSRF, sessions, débit et ressources restent actifs.
- **Recommandation de sécurité :** une terminaison HTTPS avec certificat approuvé et nom correspondant à l’adresse utilisée protège le transport et l’identité serveur. Si elle utilise un backend HTTP, empêcher l’accès Internet direct à ce backend.
- **Validation :** aucun contrôle du groupe de sécurité, de l’accès distant HTTP, du répartiteur ou des sessions sur l’instance OVHcloud n’a été réalisé.
- **Référence :** [authentification OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) : la page de connexion et les pages authentifiées nécessitent un transport protégé.

## 5. Image et dépendances — correctifs appliqués, avis résiduels à qualifier

- **OWASP :** A03 chaîne logicielle.
- **Preuve initiale :** Trivy a signalé des versions affectées de zlib et pip. Le correctif zlib a été recoupé avec [Debian DSA-6613-1](https://security-tracker.debian.org/tracker/DSA-6613-1). Aucun chemin d’exploitation HTTP de ces fonctions zlib n’a été démontré dans ce formulaire.
- **Correction :** le Dockerfile met à jour zlib et utilise pip 26.3. Les neuf avis précédents sur zlib et pip ont disparu du scan final.
- **pip-audit :** aucun avis connu sur les 23 distributions réellement installées, pip compris. Ce résultat n’est pas une preuve d’absence de vulnérabilité inconnue.
- **Trivy 0.76.2 :** 206 occurrences sur les paquets Debian, correspondant à 92 identifiants distincts ; 47 entrées HIGH, 89 MEDIUM, 65 LOW et 5 UNKNOWN. Aucun CRITICAL et aucun correctif indiqué par ce scan pour ces entrées restantes. Ces nombres ne représentent pas autant de failles HTTP exploitables de Simple App ; leur applicabilité complète n’a pas été établie.
- **Alertes SBOM :** trois avis supplémentaires mentionnent setuptools 70.3.0 dans le SBOM embarqué de pip, sans distribution setuptools installée/importable corroborée. Les scénarios décrits concernent le téléchargement de paquets ou des plateformes macOS/Windows ; ne pas les présenter comme des exploitations web établies sous Linux.
- **Preuves locales temporaires :** `/tmp/simple-app-image-audit-final.vjokEb/trivy.json` et `/tmp/simple-app-pip-audit-updated.json`. Ces fichiers ne sont pas embarqués dans l’application.
- **Reste :** qualifier les alertes restantes selon les chemins réellement utilisés, maintenir le socle et refaire le scan après reconstruction ou changement de plateforme. Le rapport ne donne pas un feu vert Internet sur le seul nombre d’alertes.

## 6. Confinement et journaux — moyen, protections ajoutées

- **OWASP :** A02, A09 journalisation, A10 traitement des erreurs.
- **Correction :** web non-root UID 1000, racine du conteneur en lecture seule, `/tmp` temporaire, capacités supprimées, élévation de privilèges bloquée, mémoire 256 Mio, un CPU et 64 processus maximum. Seuls les volumes utiles sont inscriptibles.
- **Logs :** requêtes Gunicorn et erreurs vers stdout/stderr ; rotation explicite à trois fichiers de 10 Mio. Le mot de passe commun et le corps des formulaires ne sont pas ajoutés aux journaux par l’application.
- **Vérification :** les paramètres de confinement et de rotation ont été relus sur le conteneur réellement lancé ; le mot de passe n’est pas retrouvé dans les journaux des essais. Une panne de stockage retourne 503 sans chemin ni détail SQL au client.
- **Limite :** ces mesures réduisent l’impact d’un incident ; elles ne démontrent pas l’absence de vulnérabilité du noyau ou du moteur Docker de la VM.

## 7. PostgreSQL optionnel — moyen, point restant avant usage Internet de ce mode

- **OWASP :** A02 configuration, moindre privilège.
- **Preuve :** Compose utilise un mot de passe de démonstration et le même utilisateur pour l’initialisation de PostgreSQL et l’application. L’image officielle donne des droits de superutilisateur à cet utilisateur initial.
- **Portée :** PostgreSQL est désactivé en mode texte et n’a aucun port publié sur l’hôte. Le mot de passe de démonstration ne constitue donc pas une preuve d’accès distant à la base.
- **À traiter avant usage Internet de ce mode :** secret de déploiement distinct et rôle applicatif limité à la base et aux opérations utiles. L’image PostgreSQL n’a pas été scannée dans cette revue de l’image web.

## Contrôles positifs

- Aucun point d’injection SQL identifié : valeurs transmises séparément aux requêtes paramétrées.
- HTML et login utilisateur échappés par Jinja ; une expression `{{7*7}}` reste du texte. Pas d’injection de template démontrée.
- Pas de commande système construite à partir d’une requête HTTP, ni chemin de fichier choisi par le visiteur.
- Pas d’upload, désérialisation pickle de sessions fichier, socket Docker, conteneur web privilégié ou débogueur Flask exposé identifié.
- CSP sans JavaScript, refus d’encadrement, `nosniff`, absence de referrer et de cache navigateur des pages privées.
- `config.sh` est du code local exécuté par l’administrateur ; il doit rester une source de confiance. Ce mécanisme n’est pas une injection HTTP.

## Décision de déploiement

La démonstration locale peut servir aux tests mémoire, disque local et sticky sessions. Les sources et ce rapport peuvent être publiés ; les identifiants privés et les certificats générés restent exclus de Git.

L’installation cible Ubuntu distante depuis le dépôt GitHub. Le cookie `Secure` est obligatoire et nécessite HTTPS pour les sessions navigateur. Benoit raccorde lui-même le service HTTPS ; cette modification prépare uniquement le certificat et le cookie. Le certificat autosigné générique couvre le besoin de démonstration du TP avec les avertissements de confiance et de nom décrits plus haut. Sa génération seule ne constitue pas un déploiement HTTPS. Un contrôle HTTP 200 du backend ne valide pas l’authentification par navigateur. La recette de l’instance réelle et la qualification des avis résiduels ne sont pas acquises ; ces changements ne valent pas validation de sécurité. L’accès réseau au backend doit être restreint aux sources autorisées selon le raccordement HTTPS. Le mot de passe commun doit rester hors du dépôt et être remplacé ou révoqué à la fin du TP. NFS et ses permissions seront vérifiés dans leur propre étape. Ce rapport ne constitue ni un audit d’intrusion complet ni une certification de conformité OWASP.
