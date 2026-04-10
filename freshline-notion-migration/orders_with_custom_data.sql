-- Freshline orders with custom data fields pivoted into columns
-- For Notion migration and daily sync: deduplicated to latest version per order
-- Datetime fields formatted as ISO 8601 with AEST offset for Notion date properties
-- Source: Knoxx_Freshline dataset in BigQuery (knoxx-foods-451311)

WITH orders AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_orders
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),

cd_cc_sales_order AS (
  SELECT owner_id, JSON_VALUE(value) AS cc_sales_order_id
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'order' AND key = 'carton-cloud-sales-order-id'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_qb_invoice AS (
  SELECT owner_id, JSON_VALUE(value) AS qb_invoice_id
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'order' AND key = 'quickbooksonline_invoice_id'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_backorder AS (
  SELECT owner_id, JSON_VALUE(value) AS backorder_rescheduled
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'order' AND key = 'backorder-rescheduled'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
)

SELECT
  o.id AS freshline_order_id,
  o.order_number,
  o.state,
  o.fulfillment_date,
  o.fulfillment_type,
  o.net_terms,
  o.historical,
  ROUND(o.subtotal_amount / 100.0, 2) AS subtotal,
  ROUND(o.total_amount / 100.0, 2) AS total,
  ROUND(o.tax_amount / 100.0, 2) AS tax,
  ROUND(o.fulfillment_fee_amount / 100.0, 2) AS fulfillment_fee,
  o.customer_id,
  o.contact_id,
  o.contact_name,
  o.contact_email,
  o.location_id,
  o.location_name,
  o.location_address_line1,
  o.location_address_line2,
  o.location_address_city,
  o.location_address_region,
  o.location_address_region_code,
  o.location_address_postal_code,
  o.customer_notes,
  o.internal_notes,
  o.invoice_notes,
  o.line_items_count,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S+11:00', o.opened_at, 'Australia/Sydney') AS opened_at_datetime,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S+11:00', o.confirmed_at, 'Australia/Sydney') AS confirmed_at_datetime,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S+11:00', o.completed_at, 'Australia/Sydney') AS completed_at_datetime,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S+11:00', o.cancelled_at, 'Australia/Sydney') AS cancelled_at_datetime,
  cd_cc.cc_sales_order_id,
  cd_qb.qb_invoice_id,
  CASE WHEN cd_bo.backorder_rescheduled = 'true' THEN TRUE ELSE FALSE END AS backorder_rescheduled
FROM orders o
LEFT JOIN cd_cc_sales_order cd_cc ON cd_cc.owner_id = o.id
LEFT JOIN cd_qb_invoice cd_qb ON cd_qb.owner_id = o.id
LEFT JOIN cd_backorder cd_bo ON cd_bo.owner_id = o.id
ORDER BY o.fulfillment_date DESC, o.order_number
