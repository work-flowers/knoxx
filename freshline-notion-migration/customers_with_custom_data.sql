-- Freshline customers with all custom data fields pivoted into columns
-- For Notion migration: CSV export of customer master data
-- Source: Knoxx_Freshline dataset in BigQuery (knoxx-foods-451311)

WITH customers AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_customers
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),

cd_chep AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS chep_account_number
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'chep-account-number'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_delivery_method AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS delivery_method
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'delivery-method'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_delivery_timing AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS delivery_timing
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'delivery-timing'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_notes AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS notes
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'notes'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_pallet_status AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS pallet_status
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'pallet-status'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

cd_qbo AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS quickbooks_customer_id
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'customer' AND key = 'quickbooksonline_customer_id'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
)

SELECT
  c.*,
  cd_chep.chep_account_number,
  cd_delivery_method.delivery_method,
  cd_delivery_timing.delivery_timing,
  cd_notes.notes,
  cd_pallet_status.pallet_status,
  cd_qbo.quickbooks_customer_id
FROM customers c
LEFT JOIN cd_chep ON cd_chep.owner_id = c.id
LEFT JOIN cd_delivery_method ON cd_delivery_method.owner_id = c.id
LEFT JOIN cd_delivery_timing ON cd_delivery_timing.owner_id = c.id
LEFT JOIN cd_notes ON cd_notes.owner_id = c.id
LEFT JOIN cd_pallet_status ON cd_pallet_status.owner_id = c.id
LEFT JOIN cd_qbo ON cd_qbo.owner_id = c.id
