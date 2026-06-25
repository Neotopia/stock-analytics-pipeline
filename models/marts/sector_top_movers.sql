-- Gold layer: top 3 most volatile stocks per sector over the last 7 trading days.
-- Volatility is measured by weekly_range (high - low), a simple and readable proxy.
-- Joins with the tickers seed to get sector and ETF labels for each ticker.
-- rank_in_sector lets Metabase filter to top 1, 2, or 3 within each sector.

WITH recent_prices AS (
    SELECT
        p.ticker,
        p.date,
        p.high,
        p.low,
        t.name,
        t.sector,
        t.etf
    FROM {{ ref('stg_stock_prices') }} p
    INNER JOIN {{ ref('tickers') }} t ON p.ticker = t.ticker
    WHERE t.type = 'stock'
      AND p.date >= CURRENT_DATE - INTERVAL '7 days'
),

volatility AS (
    SELECT
        ticker,
        name,
        sector,
        etf,
        ROUND((MAX(high) - MIN(low))::numeric, 2) AS weekly_range,
        ROUND(MIN(low)::numeric, 2)                AS low_price,
        ROUND(MAX(high)::numeric, 2)               AS high_price,
        COUNT(*)                                   AS trading_days
    FROM recent_prices
    GROUP BY ticker, name, sector, etf
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY sector ORDER BY weekly_range DESC) AS rank_in_sector
    FROM volatility
)

SELECT
    ticker,
    name,
    sector,
    etf,
    weekly_range,
    low_price,
    high_price,
    trading_days,
    rank_in_sector
FROM ranked
WHERE rank_in_sector <= 3
ORDER BY sector, rank_in_sector
