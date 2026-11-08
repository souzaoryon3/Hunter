-- Incremental: somente tabelas/índices novos. Aplicar em transação.
-- Compatível com os IDs integer existentes de usuarios e alertas_preco.
CREATE TABLE IF NOT EXISTS hunter_alert_state (
    alerta_id INTEGER PRIMARY KEY REFERENCES alertas_preco(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    reached BOOLEAN NOT NULL DEFAULT FALSE,
    generation BIGINT NOT NULL DEFAULT 0,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hunter_events (
    id UUID PRIMARY KEY,
    alerta_id INTEGER REFERENCES alertas_preco(id) ON DELETE SET NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    generation BIGINT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
        ('pending','published','retry','processed','cancelled','dead_pending','dead')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    publish_attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    UNIQUE (alerta_id, generation)
);
CREATE INDEX IF NOT EXISTS hunter_events_dispatch ON hunter_events(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS hunter_processing_log (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES hunter_events(id) ON DELETE CASCADE,
    phase TEXT NOT NULL CHECK (phase IN ('publish','consume','dead_letter')),
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS hunter_log_event ON hunter_processing_log(event_id, id);

CREATE TABLE IF NOT EXISTS hunter_notifications (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE REFERENCES hunter_events(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    produto TEXT NOT NULL,
    preco NUMERIC NOT NULL CHECK (preco > 0),
    preco_desejado NUMERIC NOT NULL CHECK (preco_desejado > 0),
    loja TEXT NOT NULL,
    link TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS hunter_notifications_owner ON hunter_notifications(usuario_id, id DESC);

-- Mensagens externas inválidas: guarda somente hash e código seguro, nunca corpo/token.
CREATE TABLE IF NOT EXISTS hunter_message_rejections (
    body_hash TEXT PRIMARY KEY,
    error_code TEXT NOT NULL,
    deliveries INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
