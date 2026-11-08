-- Adição independente: não altera tabelas ou produtos das outras lojas.
CREATE TABLE IF NOT EXISTS produtos_pichau (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL CHECK (length(trim(nome)) BETWEEN 2 AND 500),
    preco NUMERIC(12,2) NOT NULL CHECK (preco > 0),
    link TEXT NOT NULL UNIQUE,
    preco_cartao NUMERIC(12,2) CHECK (preco_cartao > 0),
    pagamento TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT '',
    frete_gratis BOOLEAN,
    frete_observacao TEXT NOT NULL DEFAULT 'Consulte o frete na loja conforme seu CEP.',
    disponivel BOOLEAN NOT NULL DEFAULT TRUE,
    fonte_coleta TEXT NOT NULL,
    fonte_url TEXT NOT NULL,
    coletado_em TIMESTAMPTZ NOT NULL
);
