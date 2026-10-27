# Ingestion development and operations

The workspace keeps independently deployed services in `backend/<component>`.
Production logic lives in each service's `src` packages, CLI adapters in
`scripts` or package `__main__.py`, and tests in `tests`. Fission's existing
top-level function modules remain deployment adapters; existing specs and queue
envelopes continue to work. Avoid combining these services on one Python import
path because they have compatibility modules with the same names.

## Source modules

| Source | Core modules | Destination |
| --- | --- | --- |
| YouTube | `youtube/api.py`, `youtube/youtube.py`, `youtube/records.py`, `youtube/streamer.py` | Valkey social queue |
| Bluesky live | `bluesky/filters.py`, `bluesky/streamer.py` | Valkey social queue |
| Bluesky historical | `bluesky_historical/settings.py`, `bluesky_historical/bluesky_historical.py` | Valkey social queue |
| Mastodon | `mastodon_retrieve/events.py`, `mastodon_harvest.py`, `streamer.py` | Valkey social queue |
| GDELT | `gdelt_retrieve/file_client.py`, `reader.py`, `harvesters.py`, `streamer.py`, `backfill.py`, `importer.py` | Elasticsearch |
| Threads | `threads_retrieve/parser.py`, `scraper.py`, `streamer.py` | Elasticsearch |
| AEC elections | `elections/importer.py` | Elasticsearch `aec-house-tcp` |
| ABS census | processing package `processing/process_census.py`, `processing/census_io.py` | Census queue or Elasticsearch |
| Existing social indices / NDJSON | `base/backfill.py` with script adapters | Valkey social queue |

Social messages retain `{"source": "...", "data": {...}}` and the optional
`save_common_idx` / `save_provider_idx` flags. `processing/indexer.py` checks
each destination separately before normalization and ML inference. Successful
writes register a two-hour deduplication marker. Retrying a partial delivery
repairs its missing destination. This is at-least-once processing: concurrent
deliveries may repeat inference, and Elasticsearch's stable document IDs make
the writes idempotent; the cache is not an exactly-once lock.

## Performance and failure policy

- Batch importers use bounded bulk Elasticsearch writes or one variadic Valkey
  push per batch. Census and AEC default to 500 documents per write; AEC parses
  preference CSVs in chunks of 5,000 rows. Census still reads one shapefile into
  a GeoDataFrame; its repeated column resolution and row iteration are optimized.
- Historical social replay uses batched `mget` checks instead of per-record
  `exists`, checks legacy ID aliases, keeps a bounded recent-ID cache, and stops
  if queue capacity does not recover before its configured timeout. The target
  index must already exist; incomplete existence-check responses fail the run.
- YouTube respects per-query/video limits, uses capped API pages, caches video
  statistics per run, reuses embedded replies, and propagates quota/auth failures.
  Public comment text falls back to `textDisplay` when `textOriginal` is absent.
- Bluesky and Mastodon close streams at a time limit even when no events arrive;
  retries are bounded. Live streams enqueue immediately to minimize buffering.
  A deadline during an unacknowledged queue write fails the invocation instead
  of reporting successful completion; redelivery may duplicate an accepted write.
  Bluesky whitelists use stable DIDs and expire after seven days. Topics and
  record limits still apply to whitelisted accounts.
- GDELT shares downloads, parsing and joins across live and backfill entry
  points. Downloads use reusable sessions and atomic cache replacement. All
  matching events sharing a URL survive the join. Bulk failures propagate.
  Backfills hold at most one daily dataset per worker, write each day's backup,
  and index it before scheduling further work.
- Threads separates pure parsing from optional browser dependencies. Scrolling,
  worker count and collection time are bounded. Worker and indexing failures
  propagate; blocked/interrupted runs are reported separately.
- Historical Bluesky best-effort mode exposes `failed_queries` and
  `failed_windows` and writes partial checkpoint statuses. Set
  `BLUESKY_CONTINUE_ON_ERROR=false` for immediate failure. Checkpoints are
  diagnostic snapshots; they are not automatic durable resume cursors.

Batch call counts are verified by offline tests. These are structural reductions
in network requests, not claims of measured production throughput. Live provider
latency, quotas and deployment load still determine end-to-end performance.

## Configuration and commands

Use the existing `.env` / Kubernetes secret setup. Additional controls include:

| Setting | Default / purpose |
| --- | --- |
| `YOUTUBE_MAX_VIDEOS`, `YOUTUBE_MAX_COMMENTS`, `YOUTUBE_MAX_REPLIES` | 30 / 50 / 20 |
| `YOUTUBE_MAX_RETRIES`, `YOUTUBE_QUEUE_BATCH_SIZE` | 3 retries / 100 messages |
| `BLUESKY_BATCH_SIZE`, `BLUESKY_QUEUE_LIMIT`, `BLUESKY_QUEUE_WAIT_SECONDS` | Historical: 100 / 12000 / 60 seconds |
| `BLUESKY_RECENT_IDS_LIMIT` | Historical: 10000 |
| `MASTODON_TIMEOUT_SECONDS`, `MASTODON_MAX_RETRIES` | 30 seconds / 3 retries |
| `GDELT_TARGET_ADM1`, `GDELT_ES_INDEX`, `GDELT_RAW_DIR` | Live: AS07 / gdelt-index / local temporary files |
| Threads `MAX_WORKERS`, `MAX_SCROLLS`, `KEYWORD_TIMEOUT_SECONDS`, `HARVEST_TIMEOUT_SECONDS` | 3 / 8 / 60 / 90 seconds |

GDELT settings now correctly use `GDELT_`; rename any legacy
`ELASTIC_TARGET_ADM1`, `ELASTIC_ES_INDEX`, `ELASTIC_RAW_DIR`, or other GDELT-specific
environment overrides. Elasticsearch credentials retain `ELASTIC_`.

Run package commands with the prepared environment and the component's `src`
directory as the working directory:

```shell
python -m elections --data_dir path/to/aec-csvs --batch_size 500
python -m youtube stream
python -m bluesky stream
```

The election directory must contain `GeneralPollingPlacesDownload-31496.csv`
and `HouseTcpByCandidateByPollingPlaceDownload-31496.csv`. Existing
`insert_elections_data.py` remains a compatibility CLI.

From `backend/processing/src`:

```shell
python census_upload.py --data_dir path/to/census --direct --batch_size 500
```

Omit `--direct` to publish to the census queue. Install the processing `census`
extra for shapefile input; the focused test setup already includes it.

From the repository root, with the prepared Python environment:

```shell
python backend/harvesters/scripts/gdelt_backfil_local_run.py --start 2026-01-01 --end 2026-01-02 --interval daily --max-workers 4 --index-name gdelt-index
python backend/harvesters/scripts/gdelt_upload_backup.py backup.csv --index gdelt-index --batch-size 500
python backend/harvesters/scripts/spartan_upload.py --file path/to/mastodon.ndjson
```

GDELT's backfill no longer uses dates embedded in source code. Its CLI requires
`--start` and `--end` and supports `--raw-dir`, `--backup-dir`, and `--keep-raw`.
CSV backup replay takes an explicit path and index, reads bounded batches and
uses the same normalization and failure policy as live ingestion.
The NDJSON uploader requires an explicit input file instead of a developer's
absolute local path.

Threads is optional. Add `--extra threads` to the focused `uv sync` command in
the root README, then run `uv run --no-sync python -m playwright install chromium`.
Its deployment image also needs Chromium's OS dependencies. Importing the other
harvesters and running their unit tests does not require a browser installation.

## Extending and validating

Keep provider I/O, parsing/transforms, and delivery separate. Add deterministic
fixtures for provider pagination, rejected records, duplicate IDs, partial
responses, timeouts, and storage failure. Test batch boundaries and counts to
protect performance changes. Tests must not submit to external services by
default; mark live checks `integration` and run them against configured test
services explicitly.

Run `python scripts/test_all.py` from the repository root. Each component also
supports `python -m pytest` in its own directory. `task check-python` compiles
all Python sources and checks critical static errors. See `CHANGELOG.md` for
the release's compatibility notes.

## Release validation (2026-10-28)

The Python 3.13 offline run completed with **166 passed and 18 skipped**:
18 application tests, 132 harvester tests, 14 processing tests, and 2 API query
tests passed. The skipped checks were 10 live harvester/Elasticsearch tests,
5 live API tests, and 3 inference tests requiring model artifacts. The census
tests included a real local shapefile write/read; provider and storage I/O in
unit tests used mocks. Python compilation, critical Ruff checks
(`E9,F63,F7,F82`), lockfile consistency and harvester requirements export passed.
No production data was ingested, and the live service, browser, model and
infrastructure deployments were not exercised.
