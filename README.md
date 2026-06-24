# stock-analytics-pipeline

> 🚧 **Work in progress** — this project is actively being built and extended. New layers, models, and visualizations are added incrementally as I progress through the stack.

End-to-end analytics pipeline built from scratch as a portfolio project, covering data ingestion, storage, transformation, and visualization.

## Stack

```
yfinance → PostgreSQL → dbt → Metabase (coming soon)
```

| Layer | Tool | Role |
|-------|------|------|
| Ingestion | Python · yfinance · pandas | Download stock prices from Yahoo Finance, reshape and load to PostgreSQL |
| Storage | PostgreSQL | Bronze layer (raw data) and Gold layer (transformed tables) |
| Transformation | dbt | Staging views, daily returns, top movers — tested and documented |
| Visualization | Metabase | Dashboard connected to PostgreSQL Gold layer *(in progress)* |

## Architecture

Follows the **Medallion architecture** (Bronze / Silver / Gold):

- **Bronze** — raw table `stock_prices_raw`, loaded by `load_data.py`
- **Silver** — staging view `stg_stock_prices` (cleaned, typed, filtered)
- **Gold** — marts `daily_returns`, `top_movers` (business-ready)

## Getting started

**Prerequisites:** Python 3.9+, PostgreSQL, dbt-core

```bash
# 1. Clone and install dependencies
git clone https://github.com/Neotopia/stock-analytics-pipeline.git
cd stock-analytics-pipeline
pip3 install yfinance pandas sqlalchemy psycopg2-binary python-dotenv dbt-postgres

# 2. Configure your database connection
cp .env.example .env
# Edit .env and set DATABASE_URL=postgresql://your_user@localhost:5432/your_db

# 3. Load raw data (rolling 2-year window)
python3 load_data.py

# 4. Run dbt transformations
dbt deps
dbt run
dbt test
```

## Project structure

```
stock-analytics-pipeline/
├── load_data.py          # Ingestion script: yfinance → PostgreSQL
├── .env.example          # Database connection template (never commit .env)
├── models/
│   ├── staging/          # Silver layer — stg_stock_prices
│   └── marts/            # Gold layer — daily_returns, top_movers
├── tests/                # Custom dbt singular tests
└── dbt_project.yml       # dbt configuration
```

## Key concepts practised

- pandas MultiIndex reshaping (wide → long format)
- dbt materializations: `view` for staging, `table` for marts
- dbt testing: native tests + dbt-expectations
- PostgreSQL schemas for environment isolation (dev / prod)
- Credential management with python-dotenv
- Git history rewriting with git-filter-repo

## Tickers covered

`AAPL` · `MSFT` · `GOOGL` — easily extended by editing the `TICKERS` list in `load_data.py`.
