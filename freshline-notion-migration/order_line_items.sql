-- Freshline order line items deduplicated to latest version
-- For Notion migration: one row per unique line item with FKs for relation resolution
-- Source: Knoxx_Freshline dataset in BigQuery (knoxx-foods-451311)

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
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
ORDER BY li.order_id, li.variant_sku
