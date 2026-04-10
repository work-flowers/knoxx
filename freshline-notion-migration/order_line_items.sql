-- Freshline order line items deduplicated to latest version
-- For Notion migration: one row per unique line item with FKs for relation resolution
-- Source: Knoxx_Freshline dataset in BigQuery (knoxx-foods-451311)
--
-- Ghost line item filter: li.synced_at >= o.updated_at
-- When a line item is removed from an order in Freshline, the order's updated_at
-- advances but the deleted line item is never re-synced. So any line item whose
-- synced_at is older than its parent order's updated_at is a ghost (removed).
--
-- IMPORTANT: Line items must be deduped by synced_at DESC, not updated_at DESC.
-- When an order is updated (state change, edits, etc.), Freshline re-syncs ALL
-- surviving line items with fresh synced_at values — but their updated_at only
-- changes if the line item content itself was edited. Deduping by updated_at DESC
-- is non-deterministic when multiple synced rows share the same updated_at, and
-- may pick a stale row whose synced_at predates the order's updated_at, causing
-- a false ghost-positive. (Credit: Sai identified this behaviour, 2026-04-10.)

WITH orders AS (
  SELECT id, updated_at
  FROM Knoxx_Freshline.freshline_orders
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
)

SELECT
  li.id AS freshline_line_item_id,
  li.order_id,
  li.product_id,
  li.variant_id,
  li.product_name,
  li.variant_name,
  li.variant_sku,
  li.variant_case_size,
  li.variant_unit,
  SAFE_CAST(li.unit_quantity AS FLOAT64) AS unit_quantity,
  ROUND(li.unit_price_amount / 100.0, 2) AS unit_price,
  ROUND(li.subtotal_amount / 100.0, 2) AS subtotal,
  ROUND(li.total_amount / 100.0, 2) AS total,
  ROUND(li.tax_amount / 100.0, 2) AS tax,
  SAFE_CAST(li.tax_rate AS FLOAT64) AS tax_rate,
  ROUND(li.stock_cost_amount / 100.0, 2) AS stock_cost,
  li.price_rule_type,
  li.price_rule_value,
  li.customer_notes,
  li.internal_notes,
  li.invoice_notes
FROM Knoxx_Freshline.freshline_order_line_items li
JOIN orders o ON li.order_id = o.id
WHERE li.synced_at >= o.updated_at
QUALIFY ROW_NUMBER() OVER (PARTITION BY li.id ORDER BY li.synced_at DESC) = 1
ORDER BY li.order_id, li.variant_sku
