# Changelog

## 0.2.0 — 2026-10-28

### Ingestion and processing

- Optimize all source paths: YouTube, Bluesky live/historical, Mastodon, GDELT,
  Threads, AEC elections, ABS census, and social replay/hydration/NDJSON imports.
- Add bounded pagination, retry policies, deadlines, duplicate handling, client
  cleanup, batch queue publication and bulk Elasticsearch writes.
- Fix lost GDELT events sharing article URLs, incomplete Mastodon SSE parsing,
  Bluesky whitelist limits/expiry, YouTube public comment text and video dates,
  census nonfinite values, and election CSV null serialization.
- Move duplicate checks ahead of ML inference while preserving partial-delivery
  retries and stable document IDs. Surface provider and indexing failures.

### Project structure and validation

- Extract provider protocol/parsing, transformations, settings, batch importers,
  and backfill helpers into dedicated modules. Retain Fission entry points and
  script adapters.
- Add offline source and processing regression suites, explicit live-test
  markers, isolated full-suite runner, and setup/static-check Taskfile commands.
- Validate with 166 passing offline tests and 18 explicitly skipped live/model
  tests; verify Python compilation, critical static checks, and the lockfile.
- Declare missing runtime dependencies and optional Threads/census extras;
  update the lockfile. Remove network downloads from analytics imports.
- Update root, harvesters, processing and analytics versions to 0.2.0. Other
  independently versioned services remain at 0.1.0.

### Migration notes

- GDELT-specific environment variables use `GDELT_` instead of `ELASTIC_`.
- GDELT backfills require explicit dates; NDJSON imports require an input file.
- Install NLTK assets during setup and configure `NLTK_DATA` in the application
  environment. The test runner uses the repository's `nltk_data` directory.
- Browser ingestion requires the optional Threads dependencies and Chromium.
- Live service/model tests require explicit integration opt-in. Historical
  social replay requires its destination index to exist before `mget` checks.
- Queue delivery remains at-least-once. Checkpoints describe progress and
  partial errors; they do not guarantee automatic resume or exactly-once delivery.

## 0.1.0

Initial multi-service ingestion, sentiment analysis, APIs and dashboard.
