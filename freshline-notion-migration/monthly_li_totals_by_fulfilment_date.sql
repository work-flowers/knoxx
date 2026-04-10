-- Monthly totals by fulfilment_date: LI totals + fee items.
-- Matches Notion's Total formula (Line Item Rollup Total + Fees).
--
-- Ghost filter: li.synced_at >= o.updated_at (stale LIs excluded)
-- Dedup: ROW_NUMBER() PARTITION BY id ORDER BY synced_at DESC
-- Excludes: cancelled, draft orders

WITH orders AS (
  SELECT
    id AS order_id,
    order_number,
    state,
    fulfillment_date,
    updated_at,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY synced_at DESC) AS rn
  FROM `knoxx-foods-451311.Knoxx_Freshline.freshline_orders`
),
orders_deduped AS (
  SELECT * FROM orders
  WHERE rn = 1
    AND state NOT IN ('cancelled', 'draft')
    AND fulfillment_date IS NOT NULL
),
line_items AS (
  SELECT
    id AS li_id,
    order_id,
    total_amount,
    synced_at,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY synced_at DESC) AS rn
  FROM `knoxx-foods-451311.Knoxx_Freshline.freshline_order_line_items`
),
line_items_deduped AS (
  SELECT * FROM line_items WHERE rn = 1
),
fee_items AS (
  SELECT
    id AS fee_id,
    order_id,
    total_amount,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY synced_at DESC) AS rn
  FROM `knoxx-foods-451311.Knoxx_Freshline.freshline_order_fee_items`
),
fee_items_deduped AS (
  SELECT * FROM fee_items WHERE rn = 1
),
li_totals AS (
  SELECT
    o.order_id,
    FORMAT_DATE('%Y-%m', o.fulfillment_date) AS month,
    SUM(li.total_amount / 100.0) AS li_total_aud
  FROM orders_deduped o
  JOIN line_items_deduped li
    ON li.order_id = o.order_id
    AND li.synced_at >= o.updated_at  -- ghost filter
  GROUP BY o.order_id, month
),
fee_totals AS (
  SELECT
    o.order_id,
    FORMAT_DATE('%Y-%m', o.fulfillment_date) AS month,
    SUM(fi.total_amount / 100.0) AS fee_total_aud
  FROM orders_deduped o
  JOIN fee_items_deduped fi
    ON fi.order_id = o.order_id
  GROUP BY o.order_id, month
)
SELECT
  COALESCE(lt.month, ft.month) AS month,
  COUNT(DISTINCT COALESCE(lt.order_id, ft.order_id)) AS order_count,
  ROUND(SUM(COALESCE(lt.li_total_aud, 0)), 2) AS li_total_aud,
  ROUND(SUM(COALESCE(ft.fee_total_aud, 0)), 2) AS fee_total_aud,
  ROUND(SUM(COALESCE(lt.li_total_aud, 0) + COALESCE(ft.fee_total_aud, 0)), 2) AS total_aud
FROM li_totals lt
FULL OUTER JOIN fee_totals ft
  ON lt.order_id = ft.order_id
GROUP BY month
ORDER BY month
