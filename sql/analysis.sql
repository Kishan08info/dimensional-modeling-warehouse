-- Analysis queries over the star schema.
-- Each statement is preceded by a marker comment naming it; build.py runs
-- them in order and writes one results/<name>.csv per query.

-- analysis: monthly_revenue
SELECT d.year_month AS month, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.status = 'paid'
GROUP BY d.year_month
ORDER BY d.year_month;

-- analysis: revenue_by_plan_at_order_time
SELECT dc.plan AS plan_at_order_time, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
WHERE f.status = 'paid'
GROUP BY dc.plan
ORDER BY paid_revenue DESC;

-- analysis: revenue_by_plan_current
SELECT dc2.plan AS current_plan, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
JOIN dim_customer dc2
  ON dc2.customer_id = dc.customer_id AND dc2.is_current = 1
WHERE f.status = 'paid'
GROUP BY dc2.plan
ORDER BY paid_revenue DESC;

-- analysis: revenue_by_region_at_order_time
SELECT dc.region AS region_at_order_time, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
WHERE f.status = 'paid'
GROUP BY dc.region
ORDER BY paid_revenue DESC;

-- analysis: revenue_by_region_current
SELECT dc2.region AS current_region, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
JOIN dim_customer dc2
  ON dc2.customer_id = dc.customer_id AND dc2.is_current = 1
WHERE f.status = 'paid'
GROUP BY dc2.region
ORDER BY paid_revenue DESC;

-- analysis: revenue_by_category
SELECT dp.category, COUNT(*) AS paid_orders,
       ROUND(SUM(f.amount), 2) AS paid_revenue
FROM fact_orders f
JOIN dim_product dp ON dp.product_key = f.product_key
WHERE f.status = 'paid'
GROUP BY dp.category
ORDER BY paid_revenue DESC;

-- analysis: plan_changes
SELECT COUNT(*) AS version_transitions,
       SUM(CASE WHEN new_rank > old_rank THEN 1 ELSE 0 END) AS upgrades,
       SUM(CASE WHEN new_rank < old_rank THEN 1 ELSE 0 END) AS downgrades,
       SUM(CASE WHEN new_rank = old_rank THEN 1 ELSE 0 END) AS same_plan_versions
FROM (
  SELECT customer_id,
    CASE plan WHEN 'starter' THEN 1 WHEN 'growth' THEN 2
              WHEN 'pro' THEN 3 WHEN 'enterprise' THEN 4 END AS old_rank,
    CASE LEAD(plan) OVER (PARTITION BY customer_id ORDER BY effective_from)
         WHEN 'starter' THEN 1 WHEN 'growth' THEN 2
         WHEN 'pro' THEN 3 WHEN 'enterprise' THEN 4 END AS new_rank
  FROM stg_customer_cdc
)
WHERE new_rank IS NOT NULL;

-- analysis: scd_stats
SELECT
  (SELECT COUNT(DISTINCT customer_id) FROM stg_customer_cdc) AS customers,
  (SELECT COUNT(*) FROM stg_customer_cdc) AS customer_versions,
  (SELECT COUNT(*) FROM (
     SELECT customer_id FROM stg_customer_cdc
     GROUP BY customer_id HAVING COUNT(*) > 1)) AS customers_with_changes,
  (SELECT COUNT(DISTINCT product_id) FROM stg_product_cdc) AS products,
  (SELECT COUNT(*) FROM stg_product_cdc) AS product_versions,
  (SELECT COUNT(*) FROM (
     SELECT product_id FROM stg_product_cdc
     GROUP BY product_id HAVING COUNT(*) > 1)) AS products_with_price_changes;

-- analysis: top_customers_ltv
SELECT dc2.customer_id, dc2.plan AS current_plan,
       COUNT(*) AS paid_orders, ROUND(SUM(f.amount), 2) AS lifetime_value
FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
JOIN dim_customer dc2
  ON dc2.customer_id = dc.customer_id AND dc2.is_current = 1
WHERE f.status = 'paid'
GROUP BY dc2.customer_id, dc2.plan
ORDER BY lifetime_value DESC
LIMIT 10;
