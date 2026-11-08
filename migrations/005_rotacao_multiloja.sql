-- Extensao incremental. Nenhum produto, observacao ou alerta e removido.
CREATE TABLE hunter_catalog_shops (loja TEXT PRIMARY KEY CHECK(length(trim(loja)) BETWEEN 2 AND 100));
INSERT INTO hunter_catalog_shops(loja) VALUES ('KaBuM!'),('Mercado Livre'),('Pichau');
INSERT INTO hunter_catalog_shops(loja) SELECT DISTINCT loja FROM hunter_catalog_sources ON CONFLICT DO NOTHING;
ALTER TABLE hunter_catalog_sources ADD CONSTRAINT hunter_sources_shop_fk FOREIGN KEY(loja) REFERENCES hunter_catalog_shops(loja);
ALTER TABLE hunter_catalog_products DROP CONSTRAINT hunter_catalog_products_loja_check;
ALTER TABLE hunter_catalog_products ADD CONSTRAINT hunter_products_shop_fk FOREIGN KEY(loja) REFERENCES hunter_catalog_shops(loja);
ALTER TABLE hunter_catalog_products ADD COLUMN channel TEXT NOT NULL DEFAULT 'retail' CHECK(channel IN ('retail','b2b'));
ALTER TABLE hunter_price_observations ADD COLUMN price_kind TEXT NOT NULL DEFAULT 'regular' CHECK(price_kind IN ('regular','promotional'));
ALTER TABLE hunter_price_observations ADD COLUMN promotion_terms TEXT;
ALTER TABLE hunter_price_observations ADD CONSTRAINT hunter_promotion_terms CHECK(price_kind<>'promotional' OR (promotion_terms IS NOT NULL AND length(trim(promotion_terms))>0));

ALTER TABLE hunter_catalog_sources
    ADD COLUMN adapter TEXT,
    ADD COLUMN permission_reference TEXT,
    ADD COLUMN channel TEXT NOT NULL DEFAULT 'retail' CHECK(channel IN ('retail','b2b')),
    ADD COLUMN suspended_until TIMESTAMPTZ,
    ADD COLUMN window_started_at TIMESTAMPTZ,
    ADD COLUMN products_in_window INTEGER NOT NULL DEFAULT 0 CHECK(products_in_window>=0),
    ADD COLUMN http_in_window INTEGER NOT NULL DEFAULT 0 CHECK(http_in_window>=0),
    ADD COLUMN http_request_limit INTEGER NOT NULL DEFAULT 12 CHECK(http_request_limit BETWEEN 1 AND 100),
    ADD COLUMN next_request_at TIMESTAMPTZ;
ALTER TABLE hunter_catalog_runs ADD COLUMN http_requests_reserved INTEGER NOT NULL DEFAULT 0 CHECK(http_requests_reserved>=0);

CREATE TABLE hunter_collection_control (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
    next_round_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO hunter_collection_control(singleton) VALUES(TRUE);
CREATE TABLE hunter_scheduler_heartbeat (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
    instance_id UUID NOT NULL,
    process_id INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    max_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    clock_drift_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK(state IN ('running','stopped'))
);
