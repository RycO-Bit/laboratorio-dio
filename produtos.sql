CREATE TABLE produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT,
    preco REAL,
    imagem_url TEXT,
    categoria_id INTEGER,
    media_avaliacoes REAL DEFAULT 0,
    total_avaliacoes INTEGER DEFAULT 0,
    preco_promocional REAL DEFAULT 0
);