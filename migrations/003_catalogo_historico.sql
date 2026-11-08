-- Incremental: preserva integralmente as tabelas e linhas legadas.
-- Sem backfill: nao inventar datas de coleta para precos antigos.
CREATE TABLE hunter_catalog_products (
    id BIGSERIAL PRIMARY KEY,
    loja TEXT NOT NULL CHECK (loja IN ('KaBuM!', 'Mercado Livre', 'Pichau')),
    link TEXT NOT NULL CHECK (link ~ '^https://[^/]+'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (loja, link)
);

CREATE TABLE hunter_price_observations (
    id BIGSERIAL PRIMARY KEY,
    produto_id BIGINT NOT NULL REFERENCES hunter_catalog_products(id),
    nome TEXT NOT NULL CHECK (length(trim(nome)) BETWEEN 2 AND 500),
    imagem_url TEXT CHECK (imagem_url IS NULL OR imagem_url ~ '^https://[^/]+'),
    preco NUMERIC(12,2) NOT NULL CHECK (preco > 0),
    preco_cartao NUMERIC(12,2) CHECK (preco_cartao > 0),
    pagamento TEXT,
    frete_gratis BOOLEAN,
    frete_observacao TEXT,
    disponivel BOOLEAN NOT NULL DEFAULT TRUE,
    coletado_em TIMESTAMPTZ NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    fonte_coleta TEXT NOT NULL CHECK (length(trim(fonte_coleta)) > 0),
    fonte_url TEXT NOT NULL CHECK (fonte_url ~ '^https://[^/]+'),
    UNIQUE (produto_id, coletado_em, fonte_coleta)
);
CREATE INDEX hunter_observations_latest
    ON hunter_price_observations(produto_id, coletado_em DESC, id DESC);
