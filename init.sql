CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    contenu TEXT NOT NULL CHECK (char_length(contenu) BETWEEN 1 AND 500)
);

INSERT INTO messages (contenu) VALUES
    ('Bienvenue dans Simple App.'),
    ('Ajoute ton premier message avec le formulaire.');
