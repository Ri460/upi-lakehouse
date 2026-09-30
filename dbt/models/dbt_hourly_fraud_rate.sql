SELECT dt, hr, count(*) AS transactions,
        sum(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS flagged_transactions,
        1.0*sum(CASE WHEN is_fraud THEN 1 ELSE 0 END)/count(*) AS fraud_rate
        FROM {{ source('lake', 'silver') }} GROUP BY dt, hr
