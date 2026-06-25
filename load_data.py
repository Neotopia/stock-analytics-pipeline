import io
import logging
import requests
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path
from os import environ
from dotenv import load_dotenv

load_dotenv()  # Load DATABASE_URL from .env (never committed — see .gitignore)

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Global market indices — one per geographic zone (US, France, UK, Japan, India)
# All prices (stocks AND indices) are downloaded from Yahoo Finance via yf.download().
INDICES = ["^GSPC", "^FCHI", "^FTSE", "^N225", "^BSESN"]

SEEDS_PATH    = Path(__file__).parent / "seeds" / "tickers.csv"
SEEDS_MAX_AGE = 30  # days before seeds/tickers.csv is considered stale


# ── Ticker sources ─────────────────────────────────────────────────────────────

def _fetch_spdr_holdings(etf: str, label: str, n: int = 5) -> list[dict]:
    """Download top n holdings of a SPDR ETF directly from SSGA's daily Excel file.

    SSGA publishes holdings as static Excel files (updated daily) — no JS rendering needed.
    URL pattern: holdings-daily-us-en-{etf_lowercase}.xlsx
    File structure: 4 metadata rows, then column headers, then holdings sorted by weight desc.
    """
    url = (
        "https://www.ssga.com/library-content/products/fund-data/etfs/us/"
        f"holdings-daily-us-en-{etf.lower()}.xlsx"
    )
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.raise_for_status()

    df = pd.read_excel(io.BytesIO(r.content), skiprows=4, engine="openpyxl")
    df.columns = df.columns.str.strip()

    # Keep only equity rows: Ticker is a clean uppercase symbol (no "-", no empty)
    df = df.dropna(subset=["Ticker"])
    df = df[df["Ticker"].astype(str).str.match(r"^[A-Z]{1,5}$")]

    return [
        {
            "ticker": row["Ticker"],
            "name":   row.get("Name", ""),
            "sector": label,
            "market": "US",
            "type":   "stock",
            "source": "spdr",
            "etf":    etf,
        }
        for _, row in df.head(n).iterrows()
    ]


def _fetch_wikipedia_sp500(sector_map: dict, n: int = 5) -> list[dict]:
    """Fallback: scrape S&P 500 components from Wikipedia (alphabetical, not by weight)."""
    url   = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    sp500 = pd.read_html(url)[0]
    rows: list[dict] = []
    for wiki_sector, (label, etf) in sector_map.items():
        for _, row in sp500[sp500["GICS Sector"] == wiki_sector].head(n).iterrows():
            rows.append({
                "ticker": row["Symbol"].replace(".", "-"),
                "name":   row["Security"],
                "sector": label,
                "market": "US",
                "type":   "stock",
                "source": "wikipedia_sp500",
                "etf":    etf,
            })
    return rows


def refresh_seeds_csv() -> None:
    """Refresh seeds/tickers.csv with top 5 holdings per SPDR sector ETF.

    Primary source: SSGA daily Excel files (official, weight-sorted).
    Fallback:       Wikipedia S&P 500 list (alphabetical — less precise).

    NOTE: 'source' column = how the ticker was selected (spdr / wikipedia_sp500 / manual),
    NOT where price data comes from. All prices — stocks AND indices — are downloaded
    from Yahoo Finance via yf.download() in download_prices().
    Indices are fixed by design (they don't rotate), hence source = "manual".
    """
    SECTOR_MAP = {
        "Information Technology": ("Technology",  "XLK"),
        "Financials":             ("Financial",   "XLF"),
        "Health Care":            ("Healthcare",  "XLV"),
        "Consumer Discretionary": ("Consumer",    "XLY"),
        "Energy":                 ("Energy",      "XLE"),
    }

    INDEX_ROWS: list[dict] = [
        {"ticker": "^GSPC",  "name": "S&P 500",   "sector": "", "market": "US", "type": "index", "source": "manual", "etf": ""},
        {"ticker": "^FCHI",  "name": "CAC 40",     "sector": "", "market": "FR", "type": "index", "source": "manual", "etf": ""},
        {"ticker": "^FTSE",  "name": "FTSE 100",   "sector": "", "market": "UK", "type": "index", "source": "manual", "etf": ""},
        {"ticker": "^N225",  "name": "Nikkei 225", "sector": "", "market": "JP", "type": "index", "source": "manual", "etf": ""},
        {"ticker": "^BSESN", "name": "Sensex",     "sector": "", "market": "IN", "type": "index", "source": "manual", "etf": ""},
    ]

    stock_rows: list[dict] = []
    for wiki_sector, (label, etf) in SECTOR_MAP.items():
        try:
            holdings = _fetch_spdr_holdings(etf, label, n=5)
            logger.info("  %s: %s", etf, [h["ticker"] for h in holdings])
            stock_rows.extend(holdings)
        except Exception as e:
            logger.warning("  %s SSGA failed (%s) — falling back to Wikipedia", etf, e)
            stock_rows.extend(_fetch_wikipedia_sp500({wiki_sector: (label, etf)}, n=5))

    pd.DataFrame(INDEX_ROWS + stock_rows).to_csv(SEEDS_PATH, index=False)
    logger.info("seeds/tickers.csv refreshed — %d entries", len(INDEX_ROWS) + len(stock_rows))


def get_static_tickers() -> list[str]:
    """Read the stable stock universe from seeds/tickers.csv (25 US stocks, 5 per sector).

    The CSV is curated from SPDR ETF top holdings and auto-refreshed in main()
    when it is missing or older than SEEDS_MAX_AGE days.
    """
    df = pd.read_csv(SEEDS_PATH)
    return df[df["type"] == "stock"]["ticker"].tolist()


def get_finviz_volatile(n: int = 5) -> list[str]:
    """Fetch the n most volatile stocks from the S&P 500 and NASDAQ 100.

    Queries both indices and ranks by absolute daily price change, so the
    biggest movers are captured regardless of direction (up or down).
    Restricting to two major indices ensures only well-known large caps are returned.
    Requires: pip install finvizfinance
    """
    try:
        from finvizfinance.screener.overview import Overview
        frames = []
        for index in ["S&P 500", "NASDAQ 100"]:
            screen = Overview()
            screen.set_filter(filters_dict={"Index": index})
            frames.append(screen.screener_view())

        df = pd.concat(frames).drop_duplicates("Ticker")
        df["abs_change"] = df["Change"].str.replace("%", "", regex=False).astype(float).abs()
        tickers: list[str] = df.nlargest(n, "abs_change")["Ticker"].tolist()
        logger.info("Finviz volatile (S&P 500 + NASDAQ 100): %s", tickers)
        return tickers
    except ImportError:
        logger.warning("finvizfinance not installed — run: pip install finvizfinance")
        return []
    except Exception as e:
        logger.warning("Finviz volatile unavailable (%s) — skipping", e)
        return []


def get_analyst_buys(n: int = 5) -> list[str]:
    """Fetch n S&P 500 stocks with a Strong Buy analyst consensus from Finviz.

    Analyst recommendations are aggregated from major banks and research firms.
    Strong Buy (1) is the highest consensus rating — these are the tickers with
    the broadest positive conviction from Wall Street at the time of the run.
    Volume of data: typically 50–150 S&P 500 stocks qualify at any given time;
    we take the top n by trading volume to prioritise the most liquid ones.
    Requires: pip install finvizfinance
    """
    try:
        from finvizfinance.screener.overview import Overview
        screen = Overview()
        screen.set_filter(filters_dict={
            "Index":          "S&P 500",
            "Analyst Recom.": "Strong Buy (1)",
        })
        df = screen.screener_view()
        # Parse volume (e.g. "3.21M" → 3210000) and take most liquid tickers
        df["vol_num"] = (
            df["Volume"]
            .str.replace("M", "e6", regex=False)
            .str.replace("K", "e3", regex=False)
            .astype(float)
        )
        tickers: list[str] = df.nlargest(n, "vol_num")["Ticker"].tolist()
        logger.info("Finviz analyst buys: %s", tickers)
        return tickers
    except ImportError:
        logger.warning("finvizfinance not installed — run: pip install finvizfinance")
        return []
    except Exception as e:
        logger.warning("Finviz analyst buys unavailable (%s) — skipping", e)
        return []


# ── Download & load prices ─────────────────────────────────────────────────────

def download_prices(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance and reshape to long format.

    yfinance returns a wide MultiIndex DataFrame (metric × ticker).
    stack() pivots it to long format: one row per (date, ticker).
    Indices like ^GSPC are downloaded exactly like equities.
    """
    df = yf.download(" ".join(tickers), start=start, end=end, threads=False)
    # threads=False avoids SQLite cache lock errors on Mac with multi-ticker downloads.
    df = df.stack(level=1, future_stack=True).reset_index()
    df.columns.name = None
    if "level_1" in df.columns:
        df = df.rename(columns={"level_1": "Ticker"})
    return df


def load_to_postgres(df: pd.DataFrame, engine: Engine) -> None:
    """Drop and reload stock_prices_raw in PostgreSQL (Bronze layer).

    CASCADE drops dependent dbt views (e.g. stg_stock_prices) so the table
    can be replaced cleanly. dbt run recreates them. engine.begin() handles
    commit/rollback automatically.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stock_prices_raw CASCADE"))
    df.to_sql("stock_prices_raw", engine, if_exists="replace", index=False)


# ── Load news ──────────────────────────────────────────────────────────────────

def load_news_to_postgres(tickers: list[str], engine: Engine) -> None:
    """Fetch recent news for each ticker via Finviz and store in ticker_news_raw.

    Called for the volatile tickers so Metabase can display contextual articles
    directly below the Volatility Watch section of the US dashboard.
    The table is replaced on each run (snapshot of the latest articles).
    Requires: pip install finvizfinance
    """
    try:
        from finvizfinance.ticker import finvizfinance as fvz
        all_news = []
        for ticker in tickers:
            try:
                news_df = fvz(ticker).ticker_news()
                news_df["ticker"] = ticker
                all_news.append(news_df)
            except Exception as e:
                logger.warning("No news for %s: %s", ticker, e)

        if not all_news:
            logger.warning("No news fetched — ticker_news_raw not updated")
            return

        df = pd.concat(all_news, ignore_index=True)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS ticker_news_raw"))
        df.to_sql("ticker_news_raw", engine, if_exists="replace", index=False)
        logger.info("%d news articles loaded for %s", len(df), tickers)
    except ImportError:
        logger.warning("finvizfinance not installed — run: pip install finvizfinance")
    except Exception as e:
        logger.error("News load failed: %s", e)


# ── Entrypoint ─────────────────────────────────────────────────────────────────

def main() -> None:
    end_date   = date.today()
    start_date = end_date - relativedelta(years=2)  # rolling 2-year window
    engine     = create_engine(environ["DATABASE_URL"])

    # ── 0. Refresh seeds if missing or older than SEEDS_MAX_AGE days ──────────
    seeds_age = (
        (datetime.now() - datetime.fromtimestamp(SEEDS_PATH.stat().st_mtime)).days
        if SEEDS_PATH.exists() else SEEDS_MAX_AGE + 1
    )
    if seeds_age > SEEDS_MAX_AGE:
        logger.info("seeds/tickers.csv is %d days old — refreshing from SSGA...", seeds_age)
        refresh_seeds_csv()

    # ── 1. Ticker selection (3 sources) ───────────────────────────────────────
    static_tickers  = get_static_tickers()          # seeds/tickers.csv — stable SPDR universe
    finviz_tickers  = get_finviz_volatile(n=5)      # S&P 500 + NASDAQ 100 biggest movers
    analyst_tickers = get_analyst_buys(n=5)         # Strong Buy consensus from Wall Street
    all_tickers     = list(set(static_tickers + finviz_tickers + analyst_tickers + INDICES))

    logger.info(
        "%d tickers total — %d indices · %d SPDR · %d volatile · %d analyst buys",
        len(all_tickers), len(INDICES), len(static_tickers),
        len(finviz_tickers), len(analyst_tickers),
    )

    # ── 2. Download prices ────────────────────────────────────────────────────
    try:
        df = download_prices(all_tickers, start_date, end_date)
    except Exception as e:
        logger.error("Download failed: %s", e)
        return

    # ── 3. Load prices to PostgreSQL ──────────────────────────────────────────
    try:
        load_to_postgres(df, engine)
        logger.info("%d rows loaded — %s → %s", len(df), start_date, end_date)
    except Exception as e:
        logger.error("Database load failed: %s", e)
        return

    # ── 4. Load news for volatile tickers ─────────────────────────────────────
    if finviz_tickers:
        load_news_to_postgres(finviz_tickers, engine)


if __name__ == "__main__":
    main()
