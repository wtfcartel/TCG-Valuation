-- Cardcore schema v1
--
-- Three deliberately separate layers (see docs/02-architecture.md):
--   1. MARKET DATA      raw externally sourced observations          (data_sources, card_identities, price_observations, fx_rates)
--   2. VALUATION ENGINE Cardcore's rules turning evidence into value  (methodology_*, reviewers, valuations, valuation_*)
--   3. LEDGER           what a user owned and insured, and when       (collections, assets, grading_records, ownership_events,
--                                                                      insurance_*, reports)
--
-- Ledger, evidence and valuation tables are APPEND-ONLY. UPDATE and DELETE are rejected by
-- trigger, so the state on any historical date can always be reconstructed. Corrections are
-- made by appending a new row that supersedes the old one, never by rewriting history.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION cardcore_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'cardcore: table % is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE OR REPLACE FUNCTION cardcore_make_append_only(tbl regclass) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format(
    'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION cardcore_forbid_mutation()',
    'append_only_' || replace(tbl::text, '.', '_'), tbl);
  EXECUTE format(
    'CREATE TRIGGER %I BEFORE TRUNCATE ON %s FOR EACH STATEMENT EXECUTE FUNCTION cardcore_forbid_mutation()',
    'no_truncate_' || replace(tbl::text, '.', '_'), tbl);
END $$;

-- ───────────────────────────── Identity & tenancy ─────────────────────────────

CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text NOT NULL UNIQUE CHECK (email = lower(email)),
  password_hash  text NOT NULL,
  display_name   text NOT NULL,
  role           text NOT NULL DEFAULT 'collector' CHECK (role IN ('collector', 'valuer', 'admin')),
  base_currency  char(3) NOT NULL DEFAULT 'USD',
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE collections (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  uuid NOT NULL REFERENCES users(id),
  name           text NOT NULL,
  base_currency  char(3) NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX collections_owner_idx ON collections (owner_user_id);

-- ───────────────────────────── 1. Market data ─────────────────────────────

CREATE TABLE data_sources (
  id               text PRIMARY KEY,               -- adapter code, e.g. 'manual', 'tcgdex', 'ebay_mi'
  name             text NOT NULL,
  provides         text[] NOT NULL,                -- catalogue | completed_sale | asking_price | price_guide | population
  licence_status   text NOT NULL CHECK (licence_status IN ('open', 'licensed', 'user_supplied', 'restricted', 'synthetic')),
  licence_notes    text NOT NULL,
  reliability_tier smallint NOT NULL CHECK (reliability_tier BETWEEN 1 AND 3), -- 1 = highest
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE card_identities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  game          text NOT NULL CHECK (game IN ('pokemon', 'one_piece', 'mtg', 'yugioh', 'lorcana', 'other')),
  product_type  text NOT NULL DEFAULT 'single' CHECK (product_type IN ('single', 'sealed')),
  category      text NOT NULL DEFAULT 'card',      -- card | booster_box | etb | tin | pack | other
  set_code      text NOT NULL,
  set_name      text NOT NULL,
  card_number   text,
  card_name     text NOT NULL,
  language      text NOT NULL DEFAULT 'en',
  edition       text,                               -- e.g. 1st, unlimited, shadowless
  variant       text,                               -- normal | holo | reverse_holo | alt_art | ...
  rarity        text,
  external_refs jsonb NOT NULL DEFAULT '{}'::jsonb,  -- e.g. {"tcgdex": "base1-4"}
  created_by    uuid REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX card_identities_natural_key ON card_identities
  (game, product_type, set_code, coalesce(card_number, ''), language, coalesce(edition, ''), coalesce(variant, ''), card_name);
CREATE INDEX card_identities_search_idx ON card_identities USING gin (to_tsvector('simple', card_name || ' ' || set_name || ' ' || coalesce(card_number, '')));

-- Raw evidence exactly as sourced. Asking prices and price-guide values may be stored for
-- context, but observation_kind makes it impossible to confuse them with completed sales.
CREATE TABLE price_observations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id             text NOT NULL REFERENCES data_sources(id),
  source_reference      text NOT NULL,              -- transaction ID / lot number / listing ID at the source
  source_url            text,
  card_identity_id      uuid NOT NULL REFERENCES card_identities(id),
  observation_kind      text NOT NULL CHECK (observation_kind IN ('completed_sale', 'asking_price', 'price_guide')),
  grading_company       text,
  grade                 text,
  condition             text,
  observed_at           date NOT NULL,              -- sale completion date (or quote date)
  venue                 text,
  amount_minor          bigint NOT NULL CHECK (amount_minor >= 0),
  currency              char(3) NOT NULL,
  buyers_premium_minor  bigint NOT NULL DEFAULT 0 CHECK (buyers_premium_minor >= 0),
  arms_length           boolean,                    -- null = unknown (engine rejects)
  verification_status   text NOT NULL CHECK (verification_status IN ('verified', 'unverified', 'failed')),
  verification_notes    text,
  fetched_at            timestamptz NOT NULL,
  raw_payload           jsonb NOT NULL DEFAULT '{}'::jsonb,
  ingested_by           uuid REFERENCES users(id),
  ingested_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, source_reference)
);
CREATE INDEX price_observations_identity_idx ON price_observations (card_identity_id, observed_at DESC);
SELECT cardcore_make_append_only('price_observations');

CREATE VIEW comparable_sales AS
  SELECT * FROM price_observations WHERE observation_kind = 'completed_sale';

-- 1 unit of base_currency = rate units of quote_currency, as published on rate_date.
CREATE TABLE fx_rates (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  base_currency   char(3) NOT NULL,
  quote_currency  char(3) NOT NULL,
  rate            numeric(24, 12) NOT NULL CHECK (rate > 0),
  rate_date       date NOT NULL,
  source          text NOT NULL,                    -- e.g. 'ECB reference rate', 'manual'
  source_url      text,
  recorded_by     uuid REFERENCES users(id),
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (base_currency, quote_currency, rate_date, source)
);
SELECT cardcore_make_append_only('fx_rates');

-- ───────────────────────────── 2. Valuation engine ─────────────────────────────

CREATE TABLE methodology_versions (
  id              text PRIMARY KEY,                 -- e.g. 'CSM-1.0.0'
  name            text NOT NULL,
  summary         text NOT NULL,
  parameters      jsonb NOT NULL,
  document_ref    text NOT NULL,                    -- path/URL of the narrative methodology
  effective_from  date NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
SELECT cardcore_make_append_only('methodology_versions');

CREATE TABLE reviewers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  credentials   text NOT NULL,                      -- e.g. 'CA', 'CPA'
  organisation  text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- A review validates the METHODOLOGY. It does not certify individual valuations.
CREATE TABLE methodology_reviews (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  methodology_version_id  text NOT NULL REFERENCES methodology_versions(id),
  reviewer_id             uuid NOT NULL REFERENCES reviewers(id),
  review_date             date NOT NULL,
  scope_statement         text NOT NULL,
  conclusion              text NOT NULL,
  created_at              timestamptz NOT NULL DEFAULT now()
);
SELECT cardcore_make_append_only('methodology_reviews');

-- ───────────────────────────── 3. Ledger: assets ─────────────────────────────

CREATE SEQUENCE asset_ref_seq START 1000;

-- The physical item. Its identity is fixed at creation; everything that changes over time
-- (grading, ownership, valuation, insurance) is recorded in separate append-only event tables.
CREATE TABLE assets (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_ref                 text NOT NULL UNIQUE DEFAULT ('CC-' || nextval('asset_ref_seq')),
  collection_id             uuid NOT NULL REFERENCES collections(id),
  card_identity_id          uuid NOT NULL REFERENCES card_identities(id),
  acquisition_date          date NOT NULL,
  acquisition_price_minor   bigint NOT NULL CHECK (acquisition_price_minor >= 0),  -- total for the quantity
  acquisition_currency      char(3) NOT NULL,
  acquisition_source        text,
  notes                     text,
  created_by                uuid NOT NULL REFERENCES users(id),
  created_at                timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assets_collection_idx ON assets (collection_id);
SELECT cardcore_make_append_only('assets');

CREATE TABLE grading_records (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id          uuid NOT NULL REFERENCES assets(id),
  grading_company   text,                           -- null = raw
  cert_number       text,
  grade             text,
  condition         text,                           -- raw condition (NM, LP, …) or 'sealed'
  effective_date    date NOT NULL,
  reason            text NOT NULL,                  -- 'initial', 'graded', 'regraded', 'cracked', 'correction'
  recorded_by       uuid NOT NULL REFERENCES users(id),
  recorded_at       timestamptz NOT NULL DEFAULT now(),
  CHECK ((grading_company IS NULL) = (grade IS NULL))
);
CREATE INDEX grading_records_asset_idx ON grading_records (asset_id, effective_date DESC, recorded_at DESC);
SELECT cardcore_make_append_only('grading_records');

-- Quantity held on a date = Σ acquisitions − Σ disposals/losses with effective_date ≤ date.
CREATE TABLE ownership_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id        uuid NOT NULL REFERENCES assets(id),
  event_type      text NOT NULL CHECK (event_type IN ('acquisition', 'disposal', 'loss', 'damage')),
  effective_date  date NOT NULL,
  quantity        integer NOT NULL CHECK (quantity >= 0),   -- 0 allowed for 'damage' (no change in quantity)
  amount_minor    bigint CHECK (amount_minor >= 0),         -- acquisition cost / disposal proceeds (total)
  currency        char(3),
  counterparty    text,                                     -- venue / buyer / seller
  reason          text,
  recorded_by     uuid NOT NULL REFERENCES users(id),
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  CHECK ((amount_minor IS NULL) = (currency IS NULL))
);
CREATE INDEX ownership_events_asset_idx ON ownership_events (asset_id, effective_date);
SELECT cardcore_make_append_only('ownership_events');

CREATE TABLE asset_photos (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id      uuid NOT NULL REFERENCES assets(id),
  storage_key   text NOT NULL,
  content_type  text NOT NULL,
  byte_size     integer NOT NULL,
  sha256        text NOT NULL,
  caption       text,
  uploaded_by   uuid NOT NULL REFERENCES users(id),
  uploaded_at   timestamptz NOT NULL DEFAULT now()
);
SELECT cardcore_make_append_only('asset_photos');

-- ───────────────────────────── 2b. Valuations ─────────────────────────────

CREATE TABLE valuations (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id                  uuid NOT NULL REFERENCES assets(id),
  purpose                   text NOT NULL CHECK (purpose IN ('market', 'insurance_replacement', 'historical')),
  valuation_date            date NOT NULL,          -- evidence cut-off
  status                    text NOT NULL CHECK (status IN ('concluded', 'insufficient_evidence')),
  methodology_version_id    text NOT NULL REFERENCES methodology_versions(id),
  base_currency             char(3) NOT NULL,
  subject_snapshot          jsonb NOT NULL,         -- identity + grading as valued
  quantity                  integer NOT NULL CHECK (quantity > 0),
  unit_value_minor          bigint,
  total_value_minor         bigint,
  mean_minor                bigint,
  median_minor              bigint,
  min_minor                 bigint,
  max_minor                 bigint,
  range_minor               bigint,
  dispersion_pct            numeric(10, 2),
  statistics                jsonb,                  -- full final statistics
  base_statistics           jsonb,                  -- pre-escalation statistics, if escalated
  method_used               text NOT NULL,
  window_days               integer,
  escalated                 boolean NOT NULL,
  lower_confidence          boolean NOT NULL,
  confidence                text NOT NULL CHECK (confidence IN ('high', 'moderate', 'limited')),
  confidence_factors        jsonb NOT NULL,
  confidence_reasons        jsonb NOT NULL,
  flags                     jsonb NOT NULL,
  assumptions               jsonb NOT NULL,
  inputs_hash               text NOT NULL,
  supersedes_valuation_id   uuid REFERENCES valuations(id),
  performed_by              uuid NOT NULL REFERENCES users(id),
  performed_at              timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'concluded') = (unit_value_minor IS NOT NULL))
);
CREATE INDEX valuations_asset_idx ON valuations (asset_id, purpose, valuation_date DESC, performed_at DESC);
SELECT cardcore_make_append_only('valuations');

-- Every observation considered — used AND rejected — with the reason.
CREATE TABLE valuation_comparables (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  valuation_id              uuid NOT NULL REFERENCES valuations(id),
  observation_id            uuid NOT NULL REFERENCES price_observations(id),
  included                  boolean NOT NULL,
  match_tier                text CHECK (match_tier IN ('exact', 'secondary')),
  differences               jsonb NOT NULL DEFAULT '[]'::jsonb,
  age_days                  integer NOT NULL,
  fx_rate                   numeric(24, 12),
  fx_rate_id                uuid REFERENCES fx_rates(id),
  fx_rate_date              date,
  fx_source                 text,
  basis_amount_base_minor   bigint,
  suspected_outlier         boolean NOT NULL DEFAULT false,
  deviation_from_median_pct numeric(10, 2),
  rejection_code            text,
  rejection_detail          text,
  excluded_by               uuid REFERENCES users(id),
  CHECK (included OR rejection_code IS NOT NULL),
  UNIQUE (valuation_id, observation_id)
);
SELECT cardcore_make_append_only('valuation_comparables');

-- A manual override never edits the valuation; it is layered on top with identity and reason.
CREATE TABLE valuation_overrides (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  valuation_id                uuid NOT NULL REFERENCES valuations(id),
  override_unit_value_minor   bigint NOT NULL CHECK (override_unit_value_minor >= 0),
  reason                      text NOT NULL CHECK (length(trim(reason)) >= 10),
  overridden_by               uuid NOT NULL REFERENCES users(id),
  overrider_role              text NOT NULL,
  created_at                  timestamptz NOT NULL DEFAULT now()
);
SELECT cardcore_make_append_only('valuation_overrides');

-- Effective value = latest override if any, else the computed conclusion.
CREATE VIEW valuations_effective AS
  SELECT v.*,
         o.id                          AS override_id,
         o.override_unit_value_minor,
         coalesce(o.override_unit_value_minor, v.unit_value_minor)                AS effective_unit_value_minor,
         coalesce(o.override_unit_value_minor, v.unit_value_minor) * v.quantity   AS effective_total_value_minor
  FROM valuations v
  LEFT JOIN LATERAL (
    SELECT * FROM valuation_overrides vo WHERE vo.valuation_id = v.id ORDER BY vo.created_at DESC LIMIT 1
  ) o ON true;

-- ───────────────────────────── 3b. Insurance ledger ─────────────────────────────

CREATE TABLE insurance_schedules (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id       uuid NOT NULL REFERENCES collections(id),
  insurer_name        text,
  policy_reference    text,
  customer_reference  text,
  base_currency       char(3) NOT NULL,
  -- Insurer notification rules are recorded for later use; Cardcore never computes premiums.
  notification_rules  jsonb NOT NULL DEFAULT '{"relative_change_pct": 10, "absolute_change_minor": 250000, "reconciliation": "quarterly"}'::jsonb,
  created_by          uuid NOT NULL REFERENCES users(id),
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- Hash-chained, sequenced adjustments. The declared value is never overwritten.
CREATE TABLE insurance_events (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  schedule_id              uuid NOT NULL REFERENCES insurance_schedules(id),
  seq                      integer NOT NULL,
  event_type               text NOT NULL CHECK (event_type IN
                             ('initial_declaration', 'acquisition', 'disposal', 'revaluation', 'grading_change', 'loss_damage', 'insurer_adjustment')),
  effective_date           date NOT NULL,
  previous_declared_minor  bigint NOT NULL,
  revised_declared_minor   bigint NOT NULL,
  reason                   text NOT NULL,
  methodology_version_id   text REFERENCES methodology_versions(id),
  prev_hash                text,
  event_hash               text NOT NULL,
  created_by               uuid NOT NULL REFERENCES users(id),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (schedule_id, seq)
);
SELECT cardcore_make_append_only('insurance_events');

CREATE TABLE insurance_event_lines (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id              uuid NOT NULL REFERENCES insurance_events(id),
  asset_id              uuid NOT NULL REFERENCES assets(id),
  change                text NOT NULL CHECK (change IN ('added', 'removed', 'revalued', 'adjusted')),
  quantity              integer NOT NULL,
  previous_value_minor  bigint NOT NULL,
  new_value_minor       bigint NOT NULL,
  valuation_id          uuid REFERENCES valuations(id)
);
CREATE INDEX insurance_event_lines_asset_idx ON insurance_event_lines (asset_id);
SELECT cardcore_make_append_only('insurance_event_lines');

-- Immutable report snapshots. The PDF is rendered deterministically from payload.
CREATE TABLE reports (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_type             text NOT NULL CHECK (report_type IN ('valuation', 'insurance_adjustment')),
  collection_id           uuid NOT NULL REFERENCES collections(id),
  schedule_id             uuid REFERENCES insurance_schedules(id),
  version                 integer NOT NULL,
  schema_version          text NOT NULL,
  payload                 jsonb NOT NULL,
  payload_sha256          text NOT NULL,
  methodology_version_id  text REFERENCES methodology_versions(id),
  generated_by            uuid NOT NULL REFERENCES users(id),
  generated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (collection_id, report_type, version)
);
SELECT cardcore_make_append_only('reports');

-- ───────────────────────────── Audit trail ─────────────────────────────

CREATE TABLE audit_events (
  id            bigserial PRIMARY KEY,
  actor_user_id uuid REFERENCES users(id),
  action        text NOT NULL,
  entity_type   text NOT NULL,
  entity_id     text NOT NULL,
  detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_id    text,
  occurred_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_entity_idx ON audit_events (entity_type, entity_id);
SELECT cardcore_make_append_only('audit_events');
