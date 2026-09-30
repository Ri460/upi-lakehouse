SELECT dt, merchant_id, currency,
        count(*) AS transactions,
        sum(CASE WHEN status='SUCCESS' THEN amount_paise ELSE 0 END) AS revenue_paise,
        sum(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS flagged_transactions
        FROM {{ source('lake', 'silver') }} GROUP BY dt, merchant_id, currency
