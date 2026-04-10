-- Order fee items: deduped, cents → decimal, trimmed descriptions
-- Used by the daily Freshline → Notion sync
WITH deduped AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY synced_at DESC) AS rn
  FROM `knoxx-foods-451311.Knoxx_Freshline.freshline_order_fee_items`
)
SELECT
  id AS freshline_fee_item_id,
  order_id AS freshline_order_id,
  type,
  TRIM(description) AS description,
  ROUND(subtotal_amount / 100.0, 2) AS amount,
  percentage,
  synced_at
FROM deduped
WHERE rn = 1
ORDER BY inserted_at
