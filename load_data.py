import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
from dateutil.relativedelta import relativedelta
from os import environ
from dotenv import load_dotenv

load_dotenv()  # Load DATABASE_URL from .env (never committed — see .gitignore)

# ── DATABASE ──────────────────────────────────────────────────────────────────
engine = create_engine(environ["DATABASE_URL"])

# ── TICKERS ───────────────────────────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "GOOGL"]

# ── DATE RANGE — ROLLING 2 YEARS ──────────────────────────────────────────────
# 2-year window captures at least one full market cycle (bull + correction).
# relativedelta keeps month boundaries exact across leap years.
end_date   = date.today()
start_date = end_date - relativedelta(years=2)

# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
# yfinance returns a wide MultiIndex DataFrame: level 0 = metric, level 1 = ticker.
# threads=False avoids SQLite cache lock errors on Mac with multi-ticker downloads.
df = yf.download(" ".join(TICKERS), start=start_date, end=end_date, threads=False)

# ── WIDE → LONG FORMAT ────────────────────────────────────────────────────────
# stack(level=1): pivots tickers from column level into rows (1 row per date+ticker).
# reset_index(): promotes Date and Ticker from row index back into regular columns.
df = df.stack(level=1, future_stack=True).reset_index()
df.columns.name = None              # drops residual MultiIndex name (prevents phantom column)
df = df.rename(columns={"level_1": "Ticker"})

# ── PERSIST TO POSTGRESQL (BRONZE LAYER) ─────────────────────────────────────
# CASCADE drops dependent dbt views (e.g. stg_stock_prices) so the table can be
# replaced. dbt run recreates them. text() marks the string as trusted SQL (SQLAlchemy
# safety requirement). engine.begin() handles commit/rollback automatically.
with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS stock_prices_raw CASCADE"))

df.to_sql("stock_prices_raw", engine, if_exists="replace", index=False)

print(f"✅ {len(df)} rows loaded — {start_date} → {end_date}")