-- Base inativa: nenhuma coleta, seed, backfill ou alteracao das tabelas anteriores.
CREATE TABLE hunter_catalog_sources (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
    loja TEXT NOT NULL CHECK (length(trim(loja)) BETWEEN 2 AND 100),
    integration_type TEXT NOT NULL CHECK (integration_type IN ('public_page','official_api','affiliate_feed','manual')),
    state TEXT NOT NULL DEFAULT 'disabled' CHECK (state IN ('disabled','enabled','blocked')),
    allowed_hosts TEXT[] NOT NULL CHECK (cardinality(allowed_hosts) > 0 AND array_position(allowed_hosts,NULL) IS NULL),
    interval_seconds INTEGER NOT NULL DEFAULT 21600 CHECK (interval_seconds BETWEEN 21600 AND 604800),
    request_limit INTEGER NOT NULL DEFAULT 1 CHECK (request_limit BETWEEN 1 AND 6),
    request_delay_seconds INTEGER NOT NULL DEFAULT 3 CHECK (request_delay_seconds BETWEEN 2 AND 3600),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE hunter_catalog_candidates (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES hunter_catalog_sources(id),
    original_url TEXT NOT NULL CHECK (original_url ~ '^https://[^/@?#]+/[^#]*$'),
    canonical_url TEXT NOT NULL CHECK (canonical_url ~ '^https://[^/@?#]+/[^#]*$'),
    external_id TEXT CHECK (length(external_id) BETWEEN 1 AND 200),
    seller TEXT NOT NULL DEFAULT '' CHECK (length(seller) <= 200),
    variant TEXT NOT NULL DEFAULT '' CHECK (length(variant) <= 200),
    origin TEXT NOT NULL CHECK (origin IN ('manual','existing_catalog','official_api','affiliate_feed','public_page')),
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','active','backoff','blocked','rejected','paused')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_attempt_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    error_code TEXT CHECK (error_code IN ('timeout','network','http_error','access_denied','rate_limited','invalid_data','lease_expired','manual_rejection')),
    product_id BIGINT REFERENCES hunter_catalog_products(id),
    lease_token UUID,
    lease_owner TEXT CHECK (lease_owner ~ '^[a-zA-Z0-9_-]{1,64}$'),
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(source_id, canonical_url),
    CHECK ((lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
        OR (lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK (lease_token IS NULL OR state IN ('pending','active','backoff')),
    CHECK (state <> 'rejected' OR error_code IS NOT NULL),
    CHECK (last_verified_at IS NULL OR last_attempt_at IS NOT NULL)
);
CREATE UNIQUE INDEX hunter_candidates_external_identity
    ON hunter_catalog_candidates(source_id,external_id,seller,variant) WHERE external_id IS NOT NULL;
CREATE INDEX hunter_candidates_due ON hunter_catalog_candidates(source_id,next_attempt_at,id)
    WHERE state IN ('pending','active','backoff');
CREATE INDEX hunter_candidates_state ON hunter_catalog_candidates(state,id);
CREATE INDEX hunter_candidates_product ON hunter_catalog_candidates(product_id) WHERE product_id IS NOT NULL;

CREATE TABLE hunter_catalog_runs (
    id UUID PRIMARY KEY,
    candidate_id BIGINT NOT NULL REFERENCES hunter_catalog_candidates(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    result TEXT NOT NULL DEFAULT 'running' CHECK (result IN ('running','success','failed','blocked','expired')),
    http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
    observations_inserted INTEGER NOT NULL DEFAULT 0 CHECK (observations_inserted >= 0),
    error_code TEXT CHECK (error_code IN ('timeout','network','http_error','access_denied','rate_limited','invalid_data','lease_expired','manual_rejection')),
    CHECK ((result='running' AND finished_at IS NULL) OR (result<>'running' AND finished_at IS NOT NULL)),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (result='success' OR observations_inserted=0),
    CHECK (result NOT IN ('failed','blocked','expired') OR error_code IS NOT NULL)
);
CREATE UNIQUE INDEX hunter_runs_one_running ON hunter_catalog_runs(candidate_id) WHERE result='running';
CREATE INDEX hunter_runs_candidate_time ON hunter_catalog_runs(candidate_id,started_at DESC);
