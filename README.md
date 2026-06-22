# novacart-solution

A small ETL pipeline lab. It ingests raw orders, customers, and products from a
landing area, promotes them through a medallion architecture
(Bronze → Silver → Gold), and quarantines bad records along the way.

## Quick start

```bash
pip install -r requirements.txt

# Generate sample data, run the pipeline, and run the tests in one shot
python scripts/run_everything.py

# Wipe all generated output when you're done
python scripts/cleanup.py
```

## Scripts

All scripts live in `scripts/` and are run from the repo root.

### `generate_sample_data.py`
Generates the sample source datasets in `data/landing/`:
- `data/landing/orders/orders_<date>.csv` — order CSVs for 2025-11-07 → 2025-11-10,
  including a few deliberately broken rows (zero quantity, invalid status,
  duplicates) to exercise the quarantine and dedup paths.
- `data/landing/customers/customers.json` — customer records with nested
  addresses, including one with a malformed email.
- `data/landing/products.db` — a SQLite database of products.

```bash
python scripts/generate_sample_data.py
```

### `run_everything.py`
Cross-platform end-to-end runner. Works on macOS, Linux, and Windows. Runs three
steps in order and exits on the first failure:
1. Generate sample data (`generate_sample_data.py`).
2. Run the pipeline for 2025-11-10 with a 3-day backfill (Nov 7–10).
3. Run the test suite (`pytest`).

```bash
python scripts/run_everything.py
```

### `cleanup.py`
Cleanup run **after** `run_everything.py` or any individual pipeline run. Removes
all pipeline-generated output so the next run starts from a clean slate:

```
data/bronze  data/silver  data/gold  data/quarantine  state  logs
```

It is the cross-platform equivalent of:

```bash
rm -rf data/bronze data/silver data/gold data/quarantine state logs
```

Landing/source data (`data/landing/*`) is **not** touched — regenerate that with
`generate_sample_data.py` if needed.

```bash
python scripts/cleanup.py
```

## Running the pipeline directly

```bash
# Single date
python -m src.pipeline --date 2025-11-07

# A date plus the N days before it
python -m src.pipeline --date 2025-11-10 --backfill 3
```

Pipeline behavior and paths are configured in `config/pipeline.yaml`.

## Folder overview

| Path                 | Purpose |
|----------------------|---------|
| `config/`            | Pipeline configuration (`pipeline.yaml`) — paths and stage settings. |
| `scripts/`           | Operational entry points: data generation, end-to-end runner, cleanup. |
| `src/`               | Pipeline source code. |
| `src/ingest/`        | Landing → Bronze ingestion (orders, customers, products). |
| `src/transform/`     | Bronze → Silver and Silver → Gold transforms. |
| `src/load/`          | Load helpers. |
| `src/utils/`         | Shared utilities: config loading, logging, run-state management. |
| `tests/`             | Pytest suite for schemas and pipeline scenarios. |

### Data folders (medallion layers)

These are created by the scripts/pipeline at runtime and are removed by
`cleanup.py`:

| Path                | Layer       | What lives here |
|---------------------|-------------|-----------------|
| `data/landing/`     | Source      | Raw inputs (order CSVs, customer JSON, products SQLite DB). **Persistent input** — produced by `generate_sample_data.py`, not removed by cleanup. |
| `data/bronze/`      | Bronze      | Raw data ingested as-is from landing, with minimal structure. |
| `data/silver/`      | Silver      | Cleaned, validated, and deduplicated records. |
| `data/gold/`        | Gold        | Analytics-ready dimensional model (dim_product, dim_customer, fact_orders). |
| `data/quarantine/`  | Quarantine  | Records that failed validation (bad quantity, invalid status, malformed email, etc.). |
| `state/`            | Run state   | Per-run metadata and bookkeeping written by the orchestrator. |
| `logs/`             | Logs        | Structured pipeline logs. |
