-- Evidence that users upload themselves (manual entries, CSVs, saved marketplace pages) is private to
-- the uploader: it is used only in the uploader's own valuations, and its uniqueness is per uploader,
-- so one user can neither poison nor pre-empt another user's evidence.
ALTER TABLE data_sources ADD COLUMN owner_scoped boolean NOT NULL DEFAULT false;
UPDATE data_sources SET owner_scoped = true WHERE id IN ('manual', 'csv_import', 'ebay_sold_scrape');

-- Shared-source rows use the nil UUID; owner-scoped rows use the uploader.
ALTER TABLE price_observations ADD COLUMN owner_scope uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- One-off back-fill of existing owner-scoped rows. The append-only trigger is suspended only for
-- this structural migration, inside its transaction.
ALTER TABLE price_observations DISABLE TRIGGER append_only_price_observations;
UPDATE price_observations po SET owner_scope = po.ingested_by
  FROM data_sources ds WHERE ds.id = po.source_id AND ds.owner_scoped AND po.ingested_by IS NOT NULL;
ALTER TABLE price_observations ENABLE TRIGGER append_only_price_observations;

ALTER TABLE price_observations DROP CONSTRAINT price_observations_source_id_source_reference_key;
ALTER TABLE price_observations ADD CONSTRAINT price_observations_source_ref_owner_key UNIQUE (source_id, source_reference, owner_scope);
