-- Exécuter dans une transaction : sérialiser les migrations des deux frontaux.
-- La limite inclut la date, le login et les 500 caractères du message.
SELECT pg_advisory_xact_lock(20261115, 1);
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_contenu_check;
ALTER TABLE public.messages ADD CONSTRAINT messages_contenu_check
    CHECK (char_length(contenu) BETWEEN 1 AND 600);
