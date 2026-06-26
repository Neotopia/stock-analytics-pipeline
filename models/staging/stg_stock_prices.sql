-- Silver layer — deduplicate, cast, and validate raw OHLCV prices from yfinance.
-- Quoted identifiers required: yfinance writes column names with an uppercase first letter.
--
-- Cleaning applied:
--   - DISTINCT ON (Date, Ticker): one row per day per ticker; highest volume row wins on duplicates
--   - All OHLC prices strictly positive (stocks never reach zero in valid data)
--   - Volume strictly positive (zero volume rows are unusable for whale signal detection)
--   - OHLC consistency: High is the day's ceiling, Low is the floor

SELECT DISTINCT ON ("Date", "Ticker")
    "Date"::date        AS date,
    "Ticker"            AS ticker,
    "Open"::float       AS open,
    "High"::float       AS high,
    "Low"::float        AS low,
    "Close"::float      AS close,
    "Volume"::bigint    AS volume
FROM {{ source('public', 'stock_prices_raw') }}
WHERE "Date"   IS NOT NULL
  AND "Ticker" IS NOT NULL
  AND "Open"  > 0 AND "High" > 0 AND "Low" > 0 AND "Close" > 0
  AND "Volume" > 0
  AND "High"  >= "Open" AND "High"  >= "Close"
  AND "Low"   <= "Open" AND "Low"   <= "Close"
ORDER BY "Date", "Ticker", "Volume" DESC NULLS LAST
