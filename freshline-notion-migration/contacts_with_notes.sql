-- Freshline contacts with custom data notes
-- For Notion migration: CSV export of contact records
-- Source: Knoxx_Freshline dataset in BigQuery (knoxx-foods-451311)

WITH contacts AS (
  SELECT *
  FROM Knoxx_Freshline.freshline_contacts
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
),

cd_notes AS (
  SELECT owner_id, TRIM(STRING(value), '"') AS notes
  FROM Knoxx_Freshline.freshline_custom_data
  WHERE type = 'contact' AND key = 'notes'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY updated_at DESC) = 1
)

SELECT
  c.*,
  cd_notes.notes
FROM contacts c
LEFT JOIN cd_notes ON cd_notes.owner_id = c.id
