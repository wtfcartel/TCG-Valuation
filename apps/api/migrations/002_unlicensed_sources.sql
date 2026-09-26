-- Allow sources whose data is collected without a licence (e.g. scraped marketplace pages).
-- Such evidence is usable by the engine but is always labelled in valuation and insurer reports.
ALTER TABLE data_sources DROP CONSTRAINT data_sources_licence_status_check;
ALTER TABLE data_sources ADD CONSTRAINT data_sources_licence_status_check
  CHECK (licence_status IN ('open', 'licensed', 'user_supplied', 'restricted', 'synthetic', 'unlicensed'));
