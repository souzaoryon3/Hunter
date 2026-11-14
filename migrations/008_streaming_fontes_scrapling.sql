-- Fontes emitidas pelos parsers reais existentes; 007 permanece imutavel.
CREATE OR REPLACE FUNCTION hunter_enqueue_analytics() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.fonte_coleta IN ('html_publico','http_publico','html_publico_jsonld',
                           'captura_publica','api_oficial_mercadolivre',
                           'scrapling_browser_card','scrapling_public_card') THEN
        INSERT INTO hunter_analytics_events(observation_id) VALUES(NEW.id);
    END IF;
    RETURN NEW;
END;
$$;
INSERT INTO hunter_analytics_events(observation_id,replay)
    SELECT id,TRUE FROM hunter_price_observations
    WHERE fonte_coleta IN ('scrapling_browser_card','scrapling_public_card')
    ON CONFLICT (observation_id) DO NOTHING;
