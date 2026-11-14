-- PLN de titulos publicos, sem feedback, termos pesquisados ou dados pessoais.
CREATE TABLE hunter_nlp_events (
    observation_id BIGINT PRIMARY KEY REFERENCES hunter_price_observations(id),
    replay BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','published','processed','dead_pending','dead')),
    failures INTEGER NOT NULL DEFAULT 0,
    publications INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX hunter_nlp_pending ON hunter_nlp_events(status,available_at);
CREATE TABLE hunter_text_results (
    observation_id BIGINT PRIMARY KEY REFERENCES hunter_nlp_events(observation_id),
    produto_id BIGINT NOT NULL REFERENCES hunter_catalog_products(id),
    event_time TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    replay BOOLEAN NOT NULL,
    normalized_text TEXT NOT NULL,
    tokens TEXT[] NOT NULL,
    keywords TEXT[] NOT NULL,
    category TEXT NOT NULL,
    matched_categories TEXT[] NOT NULL,
    algorithm TEXT NOT NULL
);
CREATE INDEX hunter_text_latest ON hunter_text_results(produto_id,event_time DESC,observation_id DESC);
CREATE FUNCTION hunter_enqueue_nlp() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.fonte_coleta IN ('html_publico','http_publico','html_publico_jsonld',
                           'captura_publica','api_oficial_mercadolivre',
                           'scrapling_browser_card','scrapling_public_card') THEN
        INSERT INTO hunter_nlp_events(observation_id) VALUES(NEW.id);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER hunter_observation_nlp AFTER INSERT ON hunter_price_observations
    FOR EACH ROW EXECUTE FUNCTION hunter_enqueue_nlp();
INSERT INTO hunter_nlp_events(observation_id,replay)
    SELECT id,TRUE FROM hunter_price_observations
    WHERE fonte_coleta IN ('html_publico','http_publico','html_publico_jsonld',
                          'captura_publica','api_oficial_mercadolivre',
                          'scrapling_browser_card','scrapling_public_card');
