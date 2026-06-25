# stock-analytics-pipeline

![dbt CI](https://github.com/Neotopia/stock-analytics-pipeline/actions/workflows/dbt-ci.yml/badge.svg)

> 🚧 **Work in progress** — this project is actively being built and extended. New layers, models, and visualizations are added incrementally as I progress through the stack.

End-to-end analytics pipeline built from scratch as a portfolio project, covering data ingestion, storage, transformation, and visualization.

## Stack

```
yfinance + Finviz → PostgreSQL → dbt → Metabase
```

| Layer | Tool | Role |
|-------|------|------|
| Ingestion | Python · yfinance · finvizfinance · pandas | Multi-source: SPDR ETF holdings, Finviz volatile picks, analyst buys, global indices |
| Storage | PostgreSQL | Bronze layer (raw data) — `stock_prices_raw`, `ticker_news_raw` |
| Transformation | dbt | Silver (staging) + Gold (marts) — tested and documented |
| Visualization | Metabase | Interactive dashboard connected to PostgreSQL Gold layer — date filter, KPI cards, per-market trend charts |

## Architecture

Follows the **Medallion architecture** (Bronze / Silver / Gold):

- **Bronze** — raw tables loaded by `load_data.py`: `stock_prices_raw` (OHLCV) and `ticker_news_raw` (Finviz headlines)
- **Silver** — `stg_stock_prices` (cleaned, typed, filtered — one row per ticker per day)
- **Gold** — marts ready for Metabase queries:
  - `index_performance` — 1D / YTD / 2Y returns for 5 global indices
  - `top_movers` — top 5 most volatile stocks over the last 7 days (overall)
  - `sector_top_movers` — top 3 per sector by weekly price range
  - `whale_signals` — stocks with volume > 2.5× their 20-day rolling average
  - `daily_returns` — day-over-day return per ticker

## Ticker universe

Tickers are selected dynamically from three sources and combined at runtime:

| Source | Description | Count |
|--------|-------------|-------|
| SPDR Sector ETFs | Top 5 holdings per sector (XLK, XLF, XLV, XLY, XLE) via SSGA daily Excel files | ~25 stocks |
| Finviz volatile | Most volatile S&P 500 + NASDAQ 100 stocks by absolute daily change | 5 stocks |
| Finviz analyst buys | S&P 500 stocks with Strong Buy consensus, sorted by volume | 5 stocks |
| Indices | 5 global indices: S&P 500, CAC 40, FTSE 100, Nikkei 225, Sensex | 5 indices |

The static SPDR universe is stored in `seeds/tickers.csv` and auto-refreshed when older than 30 days. Finviz picks are fetched live at each pipeline run.

## Getting started

**Prerequisites:** Python 3.9+, PostgreSQL, dbt-core

```bash
# 1. Clone and install dependencies
git clone https://github.com/Neotopia/stock-analytics-pipeline.git
cd stock-analytics-pipeline
pip3 install yfinance pandas sqlalchemy psycopg2-binary python-dotenv \
             dbt-postgres requests openpyxl finvizfinance python-dateutil

# 2. Configure your database connection
cp .env.example .env
# Edit .env and set DATABASE_URL=postgresql://your_user@localhost:5432/your_db

# 3. Load raw data (rolling 2-year window)
python3 load_data.py

# 4. Run dbt transformations
dbt deps        # install dbt_utils package
dbt seed        # load seeds/tickers.csv into PostgreSQL
dbt run
dbt test
```

## Project structure

```
stock-analytics-pipeline/
├── load_data.py          # Ingestion: SPDR + Finviz + yfinance → PostgreSQL
├── .env.example          # Database connection template (never commit .env)
├── dbt_project.yml       # dbt config (materializations, schemas)
├── packages.yml          # dbt package dependencies (dbt_utils)
├── models/
│   ├── staging/          # Silver layer — stg_stock_prices (clean, cast, filter)
│   └── marts/            # Gold layer — index_performance, top_movers, sector_top_movers, whale_signals, daily_returns
├── seeds/
│   ├── tickers.csv       # Static ticker universe (5 indices + 25 SPDR stocks)
│   └── _seeds.yml        # dbt seed documentation and tests
├── tests/                # Custom singular tests (SQL queries returning failing rows)
├── macros/               # Reusable Jinja/SQL snippets
├── analyses/             # Exploratory SQL — not materialized in the database
└── .github/workflows/    # CI/CD — dbt compile on every push
```

## CI / CD

Every push to `main` triggers a GitHub Actions workflow that installs dependencies, runs `dbt deps`, and compiles all models — validating Jinja syntax and `ref()` dependencies without requiring a live database.

> 🚧 **Planned — CI Option B:** full `dbt run` + `dbt test` against an ephemeral PostgreSQL service container spun up by GitHub Actions, with a minimal fixture dataset injected at runtime. This removes the dependency on a live database while giving complete test coverage in CI.

## Key concepts practised

- Multi-source ingestion: SSGA Excel files, Finviz screener, yfinance, news API
- pandas MultiIndex reshaping (wide → long format via `stack()`)
- Python logging module and type hints throughout
- dbt Medallion architecture: `view` for staging, `table` for marts
- dbt testing: `not_null`, `unique`, `dbt_utils.unique_combination_of_columns`
- PostgreSQL window functions: `DISTINCT ON`, `ROW_NUMBER() OVER (PARTITION BY)`, rolling averages
- Credential management with python-dotenv
- dbt seeds for reference data with auto-refresh logic
- GitHub Actions CI — dbt compile on every push (Option B with ephemeral PostgreSQL in progress)
