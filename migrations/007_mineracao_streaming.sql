-- Incremental: nao modifica produtos, observacoes, alertas ou filas anteriores.
-- Eventos antigos sao replay explicito; novas observacoes geram eventos atomicos.
CREATE TABLE hunter_analytics_events (
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
CREATE INDEX hunter_analytics_pending ON hunter_analytics_events(status,available_at);
CREATE TABLE hunter_analytics_results (
    observation_id BIGINT PRIMARY KEY REFERENCES hunter_analytics_events(observation_id),
    produto_id BIGINT NOT NULL REFERENCES hunter_catalog_products(id),
    event_time TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    replay BOOLEAN NOT NULL,
    window_size INTEGER NOT NULL CHECK (window_size BETWEEN 1 AND 20),
    price NUMERIC NOT NULL,
    mean_price NUMERIC NOT NULL,
    min_price NUMERIC NOT NULL,
    max_price NUMERIC NOT NULL,
    change_percent DOUBLE PRECISION,
    drop_detected BOOLEAN NOT NULL,
    z_score DOUBLE PRECISION,
    anomaly BOOLEAN,
    algorithm TEXT NOT NULL DEFAULT 'rolling20-v1'
);
CREATE INDEX hunter_analytics_product ON hunter_analytics_results(produto_id,event_time DESC,observation_id DESC);
CREATE FUNCTION hunter_enqueue_analytics() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.fonte_coleta IN ('html_publico','http_publico','html_publico_jsonld',
                           'captura_publica','api_oficial_mercadolivre') THEN
        INSERT INTO hunter_analytics_events(observation_id) VALUES(NEW.id);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER hunter_observation_analytics AFTER INSERT ON hunter_price_observations
    FOR EACH ROW EXECUTE FUNCTION hunter_enqueue_analytics();
INSERT INTO hunter_analytics_events(observation_id,replay)
    SELECT id,TRUE FROM hunter_price_observations
    WHERE fonte_coleta IN ('html_publico','http_publico','html_publico_jsonld',
                          'captura_publica','api_oficial_mercadolivre');
