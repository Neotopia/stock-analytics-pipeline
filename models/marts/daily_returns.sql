-- Gold layer: daily return (%) per ticker using a window function.
-- LAG(close) retrieves the previous trading day's closing price for the same ticker.
-- PARTITION BY ticker ensures the lag resets for each stock independently.

SELECT
    date,
    ticker,
    close,
    LAG(close) OVER (PARTITION BY ticker ORDER BY date)            AS prev_close,
    ROUND(
        (
            (close - LAG(close) OVER (PARTITION BY ticker ORDER BY date))
            / LAG(close) OVER (PARTITION BY ticker ORDER BY date)
            * 100
        )::numeric, 2
    )                                                               AS daily_return_pct
FROM {{ ref('stg_stock_prices') }}
