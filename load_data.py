import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
from dateutil.relativedelta import relativedelta
from os import environ
from dotenv import load_dotenv

load_dotenv()  # Load DATABASE_URL from .env (never committed — see .gitignore)

TICKERS = ["AAPL", "MSFT", "GOOGL"]


def download_prices(tickers: list, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance and reshape to long format."""
    df = yf.download(" ".join(tickers), start=start, end=end, threads=False)
    # threads=False avoids SQLite cache lock errors on Mac with multi-ticker downloads.
    # yfinance returns a wide MultiIndex DataFrame: level 0 = metric, level 1 = ticker.

    df = df.stack(level=1, future_stack=True).reset_index()
    df.columns.name = None  # drops residual MultiIndex name (prevents phantom column)

    # level_1 is the default name pandas assigns to the stacked ticker level.
    # Newer yfinance versions may already name it "Ticker" — rename only if needed.
    if "level_1" in df.columns:
        df = df.rename(columns={"level_1": "Ticker"})

    return df


def load_to_postgres(df: pd.DataFrame, engine) -> None:
    """Drop and reload stock_prices_raw in PostgreSQL (Bronze layer)."""
    # CASCADE drops dependent dbt views (e.g. stg_stock_prices) so the table can be
    # replaced. dbt run recreates them. text() marks the string as trusted SQL
    # (SQLAlchemy safety requirement). engine.begin() handles commit/rollback automatically.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stock_prices_raw CASCADE"))

    df.to_sql("stock_prices_raw", engine, if_exists="replace", index=False)


def main():
    # ── DATE RANGE — ROLLING 2 YEARS ─────────────────────────────────────────
    # 2-year window captures at least one full market cycle (bull + correction).
    # relativedelta keeps month boundaries exact across leap years.
    end_date   = date.today()
    start_date = end_date - relativedelta(years=2)

    engine = create_engine(environ["DATABASE_URL"])

    try:
        df = download_prices(TICKERS, start_date, end_date)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return

    try:
        load_to_postgres(df, engine)
        print(f"✅ {len(df)} rows loaded — {start_date} → {end_date}")
    except Exception as e:
        print(f"❌ Database load failed: {e}")


# Prevents execution when this file is imported by another script.
if __name__ == "__main__":
    main()
