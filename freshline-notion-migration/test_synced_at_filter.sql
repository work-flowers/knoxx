-- Test Sai's synced_at filter for identifying removed line items
-- Theory: if a line item was removed from an order, it won't be re-synced
-- when the order is next updated, so li.synced_at < o.updated_at
--
-- This query compares the 25 March orders that have mismatched totals:
--   1. "all" = original approach (dedup by id, no date filter)
--   2. "filtered" = Sai's approach (li.synced_at >= o.updated_at)
--   3. "remaining_diff" = how close filtered total is to order total (0 = perfect match)

WITH orders AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_orders
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),

-- Original: all line items deduped by id
li_all AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_order_line_items
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),

-- Sai's filter: only line items synced at or after the order's last update
li_filtered AS (
  SELECT li.*
  FROM Knoxx_Freshline.freshline_order_line_items li
  JOIN orders o ON li.order_id = o.id
  WHERE li.synced_at >= o.updated_at
  QUALIFY ROW_NUMBER() OVER (PARTITION BY li.id ORDER BY li.updated_at DESC) = 1
),

li_all_totals AS (
  SELECT order_id, COUNT(*) AS li_count, ROUND(SUM(total_amount / 100.0), 2) AS li_total
  FROM li_all GROUP BY order_id
),

li_filtered_totals AS (
  SELECT order_id, COUNT(*) AS li_count, ROUND(SUM(total_amount / 100.0), 2) AS li_total
  FROM li_filtered GROUP BY order_id
)

SELECT
  o.order_number,
  o.location_name AS customer,
  ROUND(o.total_amount / 100.0, 2) AS order_total,
  la.li_count AS all_li_count,
  la.li_total AS all_li_total,
  lf.li_count AS filtered_li_count,
  lf.li_total AS filtered_li_total,
  ROUND(COALESCE(lf.li_total, 0) - ROUND(o.total_amount / 100.0, 2), 2) AS remaining_diff
FROM orders o
LEFT JOIN li_all_totals la ON la.order_id = o.id
LEFT JOIN li_filtered_totals lf ON lf.order_id = o.id
WHERE o.fulfillment_date >= '2026-03-01' AND o.fulfillment_date < '2026-04-01'
  AND o.state NOT IN ('cancelled', 'draft')
  AND ROUND(o.total_amount / 100.0, 2) != COALESCE(la.li_total, 0)
ORDER BY ABS(COALESCE(la.li_total, 0) - ROUND(o.total_amount / 100.0, 2)) DESC;


-- Bonus: aggregate check — does the filtered total match the order total across ALL March orders?
WITH orders AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_orders
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),
li_filtered AS (
  SELECT li.*
  FROM Knoxx_Freshline.freshline_order_line_items li
  JOIN orders o ON li.order_id = o.id
  WHERE li.synced_at >= o.updated_at
  QUALIFY ROW_NUMBER() OVER (PARTITION BY li.id ORDER BY li.updated_at DESC) = 1
)

SELECT
  'March orders excl cancelled+draft' AS scope,
  COUNT(DISTINCT o.id) AS order_count,
  ROUND(SUM(DISTINCT ROUND(o.total_amount / 100.0, 2)), 2) AS order_level_total,
  ROUND(SUM(lf.total_amount / 100.0), 2) AS filtered_li_total,
  COUNT(lf.id) AS filtered_li_count
FROM orders o
LEFT JOIN li_filtered lf ON lf.order_id = o.id
WHERE o.fulfillment_date >= '2026-03-01' AND o.fulfillment_date < '2026-04-01'
  AND o.state NOT IN ('cancelled', 'draft');
