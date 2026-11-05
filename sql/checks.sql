-- Data tests for the star schema.
-- Each statement is preceded by a marker comment naming it; build.py runs
-- them in order and every one must return 0 violations.

-- check: duplicate_customer_keys
SELECT COUNT(*) FROM (
  SELECT customer_key FROM dim_customer GROUP BY customer_key HAVING COUNT(*) > 1
);

-- check: duplicate_product_keys
SELECT COUNT(*) FROM (
  SELECT product_key FROM dim_product GROUP BY product_key HAVING COUNT(*) > 1
);

-- check: overlapping_customer_ranges
SELECT COUNT(*) FROM dim_customer a
JOIN dim_customer b
  ON a.customer_id = b.customer_id AND a.customer_key < b.customer_key
 AND a.effective_from <= COALESCE(b.effective_to, '9999-12-31')
 AND COALESCE(a.effective_to, '9999-12-31') >= b.effective_from;

-- check: overlapping_product_ranges
SELECT COUNT(*) FROM dim_product a
JOIN dim_product b
  ON a.product_id = b.product_id AND a.product_key < b.product_key
 AND a.effective_from <= COALESCE(b.effective_to, '9999-12-31')
 AND COALESCE(a.effective_to, '9999-12-31') >= b.effective_from;

-- check: invalid_effective_ranges
SELECT COUNT(*) FROM dim_customer
WHERE effective_to IS NOT NULL AND effective_to < effective_from;

-- check: unresolved_customer_orders
SELECT COUNT(*) FROM stg_orders o
WHERE NOT EXISTS (
  SELECT 1 FROM dim_customer dc
  WHERE dc.customer_id = o.customer_id
    AND dc.effective_from <= o.order_date
    AND (dc.effective_to IS NULL OR dc.effective_to >= o.order_date)
);

-- check: unresolved_product_orders
SELECT COUNT(*) FROM stg_orders o
WHERE NOT EXISTS (
  SELECT 1 FROM dim_product dp
  WHERE dp.product_id = o.product_id
    AND dp.effective_from <= o.order_date
    AND (dp.effective_to IS NULL OR dp.effective_to >= o.order_date)
);

-- check: fact_row_count_matches_raw
SELECT ABS((SELECT COUNT(*) FROM fact_orders) - (SELECT COUNT(*) FROM stg_orders));

-- check: paid_revenue_reconciles
SELECT ABS(ROUND(
  (SELECT SUM(amount) FROM fact_orders WHERE status = 'paid')
  - (SELECT SUM(CAST(amount AS REAL)) FROM stg_orders WHERE status = 'paid'), 2));

-- check: current_customer_count
SELECT ABS(
  (SELECT COUNT(*) FROM dim_customer WHERE is_current = 1)
  - (SELECT COUNT(DISTINCT customer_id) FROM stg_customer_cdc));

-- check: plan_attribution_correct
SELECT COUNT(*) FROM fact_orders f
JOIN dim_customer dc ON dc.customer_key = f.customer_key
JOIN stg_orders o ON o.order_id = f.order_id
WHERE dc.plan <> (
  SELECT c.plan FROM stg_customer_cdc c
  WHERE c.customer_id = o.customer_id AND c.effective_from <= o.order_date
  ORDER BY c.effective_from DESC LIMIT 1
);

-- check: amount_matches_price_asof
SELECT COUNT(*) FROM fact_orders f
JOIN dim_product dp ON dp.product_key = f.product_key
JOIN stg_orders o ON o.order_id = f.order_id
WHERE ROUND(f.amount, 2) <> ROUND(dp.price * CAST(o.quantity AS INTEGER), 2);
