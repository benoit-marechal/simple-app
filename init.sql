CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    contenu TEXT NOT NULL CONSTRAINT messages_contenu_check CHECK (char_length(contenu) BETWEEN 1 AND 600)
);

INSERT INTO messages (contenu) VALUES
    ('Bienvenue dans Simple App.'),
    ('Ajouter un message avec le formulaire.');
