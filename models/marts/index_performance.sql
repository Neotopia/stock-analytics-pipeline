-- Gold layer: daily, YTD, and 2-year performance for each market index.
-- Joins stg_stock_prices with the tickers seed to isolate indices (type = 'index').
-- Uses DISTINCT ON (PostgreSQL-specific) to efficiently pick anchor-date prices.

WITH prices AS (
    SELECT
        p.ticker,
        p.date,
        p.close,
        t.name,
        t.market,
        -- Previous trading day close — used for 1-day return
        LAG(p.close) OVER (PARTITION BY p.ticker ORDER BY p.date) AS close_prev_day
    FROM {{ ref('stg_stock_prices') }} p
    INNER JOIN {{ ref('tickers') }} t ON p.ticker = t.ticker
    WHERE t.type = 'index'
),

-- Most recent available close per index
latest AS (
    SELECT DISTINCT ON (ticker)
        ticker, name, market, date AS latest_date, close, close_prev_day
    FROM prices
    ORDER BY ticker, date DESC
),

-- First trading day of the current year per index (YTD baseline)
ytd_base AS (
    SELECT DISTINCT ON (ticker) ticker, close AS close_ytd_start
    FROM prices
    WHERE EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE)
    ORDER BY ticker, date ASC
),

-- Earliest available date per index (≈ 2 years ago, start of the rolling window)
two_year_base AS (
    SELECT DISTINCT ON (ticker) ticker, close AS close_2y_start
    FROM prices
    ORDER BY ticker, date ASC
)

SELECT
    l.ticker,
    l.name,
    l.market,
    l.latest_date,
    ROUND(l.close::numeric, 2)                                                        AS close,
    ROUND(((l.close - l.close_prev_day) / l.close_prev_day * 100)::numeric, 2)       AS return_1d_pct,
    ROUND(((l.close - y.close_ytd_start)  / y.close_ytd_start  * 100)::numeric, 2)  AS return_ytd_pct,
    ROUND(((l.close - t.close_2y_start)   / t.close_2y_start   * 100)::numeric, 2)  AS return_2y_pct
FROM latest l
LEFT JOIN ytd_base      y ON l.ticker = y.ticker
LEFT JOIN two_year_base t ON l.ticker = t.ticker
ORDER BY l.market
