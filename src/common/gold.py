# Integer paise prevents floating-point accumulation in revenue totals.
QUERIES = {
    "daily_merchant_revenue": """SELECT dt, merchant_id, currency,
        count(*) AS transactions,
        sum(CASE WHEN status='SUCCESS' THEN amount_paise ELSE 0 END) AS revenue_paise,
        sum(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS flagged_transactions
        FROM silver GROUP BY dt, merchant_id, currency""",
    "hourly_fraud_rate": """SELECT dt, hr, count(*) AS transactions,
        sum(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS flagged_transactions,
        1.0*sum(CASE WHEN is_fraud THEN 1 ELSE 0 END)/count(*) AS fraud_rate
        FROM silver GROUP BY dt, hr""",
    "payment_method_mix": """SELECT payment_method, count(*) AS transactions,
        sum(CASE WHEN status='SUCCESS' THEN amount_paise ELSE 0 END) AS revenue_paise
        FROM silver GROUP BY payment_method""",
}
