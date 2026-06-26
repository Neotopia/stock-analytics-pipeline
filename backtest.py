"""
Backtest — Whale Signal Strategy
=================================
Signal  : volume > 2.5× 20-day rolling average (from `whale_signals` Gold model)
Entry   : open price the next trading day after the signal
Exit    : close price after N trading days (tested for 3, 5, and 10 days)
Benchmark: S&P 500 (^GSPC) buy-and-hold return over the same holding window

Results are saved to the `backtest_whale_signals` PostgreSQL table.
Run with: python3 backtest.py
"""

import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Parameters ─────────────────────────────────────────────────────────────────

HOLD_PERIODS  = [3, 5, 10]   # trading days to hold the position
OUTPUT_TABLE  = "backtest_whale_signals"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load whale signals and full price history from PostgreSQL."""

    logger.info("Loading whale signals from Gold layer...")
    signals = pd.read_sql(
        """
        SELECT ws.ticker, ws.date AS signal_date, ws.sector
        FROM public.whale_signals ws
        ORDER BY ws.ticker, ws.date
        """,
        engine,
        parse_dates=["signal_date"],
    )
    logger.info("  → %d signals found for %d tickers", len(signals), signals["ticker"].nunique())

    tickers = signals["ticker"].unique().tolist() + ["^GSPC"]
    logger.info("Loading price history for %d tickers + S&P 500 benchmark...", len(tickers))
    prices = pd.read_sql(
        """
        SELECT ticker, date, open, close
        FROM public.stg_stock_prices
        WHERE ticker = ANY(%(tickers)s)
        ORDER BY ticker, date
        """,
        engine,
        params={"tickers": tickers},
        parse_dates=["date"],
    )
    logger.info("  → %d price rows loaded", len(prices))

    return signals, prices


# ── Core backtest logic ────────────────────────────────────────────────────────

def run_backtest(signals: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate all whale signal trades across all hold periods.

    For each signal:
      - Entry  = open of the next trading day after the signal date
      - Exit   = close N trading days after entry
      - Benchmark return = S&P 500 close-to-close over the same window
    """
    # Index prices by ticker for fast lookup
    price_map: dict[str, pd.DataFrame] = {
        ticker: grp.sort_values("date").reset_index(drop=True)
        for ticker, grp in prices.groupby("ticker")
    }
    spx = price_map.get("^GSPC")

    all_trades: list[dict] = []

    for _, signal in signals.iterrows():
        ticker      = signal["ticker"]
        signal_date = signal["signal_date"]
        sector      = signal["sector"]

        ticker_prices = price_map.get(ticker)
        if ticker_prices is None:
            continue

        # Locate the signal date in the price series
        signal_idx_list = ticker_prices.index[ticker_prices["date"] == signal_date].tolist()
        if not signal_idx_list:
            continue
        signal_idx = signal_idx_list[0]

        # Entry = open of next trading day
        entry_idx = signal_idx + 1
        if entry_idx >= len(ticker_prices):
            continue
        entry_row   = ticker_prices.loc[entry_idx]
        entry_date  = entry_row["date"]
        entry_price = entry_row["open"]

        if pd.isna(entry_price) or entry_price <= 0:
            continue

        for hold_days in HOLD_PERIODS:
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(ticker_prices):
                continue

            exit_row   = ticker_prices.loc[exit_idx]
            exit_date  = exit_row["date"]
            exit_price = exit_row["close"]

            if pd.isna(exit_price) or exit_price <= 0:
                continue

            trade_return = (exit_price - entry_price) / entry_price * 100

            # Benchmark: S&P 500 return over the same calendar window
            bench_return = None
            if spx is not None:
                spx_entry = spx[spx["date"] == entry_date]
                spx_exit  = spx[spx["date"] == exit_date]
                if not spx_entry.empty and not spx_exit.empty:
                    spx_entry_price = spx_entry.iloc[0]["close"]
                    spx_exit_price  = spx_exit.iloc[0]["close"]
                    if spx_entry_price > 0:
                        bench_return = (spx_exit_price - spx_entry_price) / spx_entry_price * 100

            alpha = (trade_return - bench_return) if bench_return is not None else None

            all_trades.append({
                "ticker":          ticker,
                "sector":          sector,
                "signal_date":     signal_date.date(),
                "entry_date":      entry_date.date(),
                "entry_price":     round(entry_price, 4),
                "exit_date":       exit_date.date(),
                "exit_price":      round(exit_price, 4),
                "hold_days":       hold_days,
                "return_pct":      round(trade_return, 4),
                "bench_return_pct": round(bench_return, 4) if bench_return is not None else None,
                "alpha_pct":       round(alpha, 4) if alpha is not None else None,
                "profitable":      trade_return > 0,
            })

    return pd.DataFrame(all_trades)


# ── Summary stats ──────────────────────────────────────────────────────────────

def print_summary(trades: pd.DataFrame) -> None:
    """Print a concise summary of backtest results by hold period."""
    print("\n" + "=" * 60)
    print("WHALE SIGNAL BACKTEST — SUMMARY")
    print("=" * 60)

    for hold_days in HOLD_PERIODS:
        subset = trades[trades["hold_days"] == hold_days]
        if subset.empty:
            continue

        n         = len(subset)
        win_rate  = subset["profitable"].mean() * 100
        avg_ret   = subset["return_pct"].mean()
        med_ret   = subset["return_pct"].median()
        best      = subset["return_pct"].max()
        worst     = subset["return_pct"].min()
        avg_alpha = subset["alpha_pct"].mean() if "alpha_pct" in subset else None

        print(f"\n  Hold {hold_days:>2} days  │  {n} trades")
        print(f"  Win rate        {win_rate:>6.1f}%")
        print(f"  Avg return      {avg_ret:>+6.2f}%   (median {med_ret:>+.2f}%)")
        print(f"  Best / Worst    {best:>+.2f}% / {worst:>+.2f}%")
        if avg_alpha is not None:
            print(f"  Avg alpha vs SPX {avg_alpha:>+.2f}%")

    print("\n  Top 5 trades (by return):")
    cols = ["ticker", "signal_date", "hold_days", "return_pct", "alpha_pct"]
    top5 = trades.nlargest(5, "return_pct")[cols].to_string(index=False)
    for line in top5.splitlines():
        print(f"    {line}")
    print("=" * 60 + "\n")


# ── Persistence ────────────────────────────────────────────────────────────────

def save_results(trades: pd.DataFrame, engine) -> None:
    """Write backtest results to PostgreSQL, replacing any prior run."""
    logger.info("Saving %d trade records to '%s'...", len(trades), OUTPUT_TABLE)
    trades.to_sql(
        OUTPUT_TABLE,
        engine,
        schema="public",
        if_exists="replace",
        index=False,
    )
    logger.info("  → Done.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise EnvironmentError("DATABASE_URL not set — check your .env file.")

    engine = create_engine(db_url)

    signals, prices = load_data(engine)

    logger.info("Running backtest for hold periods %s...", HOLD_PERIODS)
    trades = run_backtest(signals, prices)

    if trades.empty:
        logger.warning("No trades generated — check that whale_signals has data.")
        return

    logger.info("  → %d trades simulated", len(trades))
    print_summary(trades)
    save_results(trades, engine)


if __name__ == "__main__":
    main()
