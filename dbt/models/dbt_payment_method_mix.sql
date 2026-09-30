SELECT payment_method, count(*) AS transactions,
        sum(CASE WHEN status='SUCCESS' THEN amount_paise ELSE 0 END) AS revenue_paise
        FROM {{ source('lake', 'silver') }} GROUP BY payment_method
