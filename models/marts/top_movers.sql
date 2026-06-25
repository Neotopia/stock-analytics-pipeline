-- Gold layer: top 5 most volatile stocks over the last 7 trading days (overall ranking).
-- Filters to stocks only — indices are excluded because their absolute price levels
-- (e.g. S&P 500 at ~5800) would dominate the weekly_range ranking against individual stocks.
-- For a per-sector breakdown, see sector_top_movers.

SELECT
    p.ticker,
    ROUND((MAX(p.high) - MIN(p.low))::numeric, 2) AS weekly_range,
    ROUND(MIN(p.low)::numeric, 2)                  AS low_price,
    ROUND(MAX(p.high)::numeric, 2)                 AS high_price,
    COUNT(*)                                        AS trading_days
FROM {{ ref('stg_stock_prices') }} p
INNER JOIN {{ ref('tickers') }} t ON p.ticker = t.ticker
WHERE t.type = 'stock'
  AND p.date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY p.ticker
ORDER BY weekly_range DESC
LIMIT 5
