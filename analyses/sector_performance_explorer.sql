-- Exploratory analysis: sector performance over the last 30 days
-- Not materialized in the database — run manually with dbt compile + psql, or paste in Metabase.
--
-- For each sector, computes:
--   - average daily return across all stocks in the sector
--   - best and worst performer by total return over the window
--   - number of trading days covered

WITH daily AS (
    SELECT
        dr.ticker,
        dr.date,
        dr.return_pct,
        t.sector
    FROM {{ ref('daily_returns') }} dr
    INNER JOIN {{ ref('tickers') }} t ON dr.ticker = t.ticker
    WHERE t.type   = 'stock'
      AND t.sector IS NOT NULL
      AND dr.date  >= CURRENT_DATE - INTERVAL '30 days'
),

sector_summary AS (
    SELECT
        sector,
        COUNT(DISTINCT ticker)            AS num_tickers,
        COUNT(*)                          AS total_observations,
        ROUND(AVG(return_pct)::numeric, 3) AS avg_daily_return_pct,
        ROUND(MIN(return_pct)::numeric, 3) AS worst_day_pct,
        ROUND(MAX(return_pct)::numeric, 3) AS best_day_pct
    FROM daily
    GROUP BY sector
),

-- Cumulative return per ticker over the window (product of daily returns)
ticker_cumulative AS (
    SELECT
        ticker,
        sector,
        ROUND(
            ((EXP(SUM(LN(1 + return_pct / 100))) - 1) * 100)::numeric, 2
        ) AS cumulative_return_pct
    FROM daily
    GROUP BY ticker, sector
),

best_in_sector AS (
    SELECT DISTINCT ON (sector)
        sector,
        ticker  AS best_ticker,
        cumulative_return_pct AS best_return_pct
    FROM ticker_cumulative
    ORDER BY sector, cumulative_return_pct DESC
),

worst_in_sector AS (
    SELECT DISTINCT ON (sector)
        sector,
        ticker  AS worst_ticker,
        cumulative_return_pct AS worst_return_pct
    FROM ticker_cumulative
    ORDER BY sector, cumulative_return_pct ASC
)

SELECT
    s.sector,
    s.num_tickers,
    s.avg_daily_return_pct,
    s.worst_day_pct,
    s.best_day_pct,
    b.best_ticker,
    b.best_return_pct,
    w.worst_ticker,
    w.worst_return_pct
FROM sector_summary   s
LEFT JOIN best_in_sector  b ON s.sector = b.sector
LEFT JOIN worst_in_sector w ON s.sector = w.sector
ORDER BY s.avg_daily_return_pct DESC
