-- Singular test: all market codes in index_performance must be known ISO codes.
-- dbt runs this query and fails if it returns any rows.

SELECT ticker, market
FROM {{ ref('index_performance') }}
WHERE market NOT IN ('US', 'FR', 'UK', 'JP', 'IN')
