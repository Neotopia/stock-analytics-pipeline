-- Silver layer: cast, rename, and filter raw stock prices loaded by load_data.py.
-- Quoted column names (e.g. "Date") are required because yfinance writes them
-- with an uppercase first letter — PostgreSQL treats unquoted names as lowercase.

SELECT
    "Date"::date       AS date,
    "Ticker"           AS ticker,
    "Open"::float      AS open,
    "High"::float      AS high,
    "Low"::float       AS low,
    "Close"::float     AS close,
    "Volume"::bigint   AS volume
FROM {{ source('public', 'stock_prices_raw') }}
WHERE "Date"   IS NOT NULL
  AND "Ticker" IS NOT NULL
  AND "Close"  > 0        -- excludes rows with missing or zero closing price
