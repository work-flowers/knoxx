---
name: freshline-notion-sync
description: Daily sync of Freshline orders and line items from BigQuery into Notion — creates new records, updates changed ones, and archives deleted test orders.
---

You are performing the daily Freshline → Notion sync for Knoxx Foods. This syncs order and line item data from BigQuery (Fivetran-replicated Freshline data) into Notion databases.

## BigQuery Project
- Project ID: `knoxx-foods-451311`
- Dataset: `Knoxx_Freshline`

## Notion Data Source IDs (use the `notion-knoxx` MCP connector)
- Orders: `b04f62ec-bb3d-448b-852e-8ac82433bec1`
- Order Line Items: `33c8094c-3d8a-8074-a5b3-000bc7dad468`
- Products: `b5fcd582-adaf-4acb-84b0-0c958fd0f630`
- Customers: `313fc228-6e0d-490e-b425-51a72d069a70`
- Contacts: `a79c5d05-0422-4b50-832c-2386c4280949`

## Key File Paths (in the mounted workspace)
The workspace mount path changes each session. To find the correct base path, run:
```bash
ls /sessions/*/mnt/knoxx/freshline-notion-migration/ 2>/dev/null
```
All files are under `<workspace-mount>/knoxx/freshline-notion-migration/`:
- `orders-data.csv` — Previous BQ extract of orders (baseline for diffing)
- `order-line-items-data.csv` — Previous BQ extract of line items (baseline for diffing)
- `existing-order-ids.json` — Map of `freshline_order_id → Notion page_id` for all orders already in Notion
- `existing-line-item-ids.json` — Map of `freshline_line_item_id → Notion page_id` for all line items already in Notion
- `lookup-customers.json` — Map of `freshline_customer_id → Notion page_id`
- `lookup-contacts.json` — Map of `contact_email → {page_id, name}`
- `lookup-products.json` — Map of `freshline_variant_id → Notion page_id`

## Step 1: Extract from BigQuery

Run these two queries using the BigQuery MCP connector (`execute_sql_readonly`, projectId `knoxx-foods-451311`):

**Orders query:**
```sql
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
  o.id AS freshline_order_id, o.order_number, o.state, o.fulfillment_date, o.fulfillment_type,
  o.net_terms, o.historical,
  ROUND(o.subtotal_amount / 100.0, 2) AS subtotal,
  ROUND(o.total_amount / 100.0, 2) AS total,
  ROUND(o.tax_amount / 100.0, 2) AS tax,
  ROUND(o.fulfillment_fee_amount / 100.0, 2) AS fulfillment_fee,
  o.customer_id, o.contact_id, o.contact_name, o.contact_email,
  o.location_id, o.location_name, o.location_address_line1, o.location_address_line2,
  o.location_address_city, o.location_address_region, o.location_address_region_code,
  o.location_address_postal_code,
  o.customer_notes, o.internal_notes, o.invoice_notes, o.line_items_count,
  FORMAT_DATE('%Y-%m-%d', DATE(o.opened_at, 'Australia/Sydney')) AS opened_at_date,
  FORMAT_DATE('%Y-%m-%d', DATE(o.confirmed_at, 'Australia/Sydney')) AS confirmed_at_date,
  FORMAT_DATE('%Y-%m-%d', DATE(o.completed_at, 'Australia/Sydney')) AS completed_at_date,
  FORMAT_DATE('%Y-%m-%d', DATE(o.cancelled_at, 'Australia/Sydney')) AS cancelled_at_date,
  cd_cc.cc_sales_order_id, cd_qb.qb_invoice_id,
  CASE WHEN cd_bo.backorder_rescheduled = 'true' THEN TRUE ELSE FALSE END AS backorder_rescheduled
FROM orders o
LEFT JOIN cd_cc_sales_order cd_cc ON cd_cc.owner_id = o.id
LEFT JOIN cd_qb_invoice cd_qb ON cd_qb.owner_id = o.id
LEFT JOIN cd_backorder cd_bo ON cd_bo.owner_id = o.id
ORDER BY o.fulfillment_date DESC, o.order_number
```

**Line items query:**
```sql
SELECT
  li.id AS freshline_line_item_id, li.order_id, li.product_id, li.variant_id,
  li.product_name, li.variant_name, li.variant_sku, li.variant_case_size, li.variant_unit,
  SAFE_CAST(li.unit_quantity AS FLOAT64) AS unit_quantity,
  ROUND(li.unit_price_amount / 100.0, 2) AS unit_price,
  ROUND(li.subtotal_amount / 100.0, 2) AS subtotal,
  ROUND(li.total_amount / 100.0, 2) AS total,
  ROUND(li.tax_amount / 100.0, 2) AS tax,
  SAFE_CAST(li.tax_rate AS FLOAT64) AS tax_rate,
  ROUND(li.stock_cost_amount / 100.0, 2) AS stock_cost,
  li.price_rule_type, li.price_rule_value,
  li.customer_notes, li.internal_notes, li.invoice_notes
FROM Knoxx_Freshline.freshline_order_line_items li
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
ORDER BY li.order_id, li.variant_sku
```

The BQ results will be large and saved to files. Use a Python script or subagent to parse them.

## Step 2: Diff Against Existing Data

Write a Python script that:
1. Parses the BQ JSON results (schema: `{rows: [{f: [{v: value}]}], schema: {fields: [{name}]}}`)
2. Loads the old CSVs (`orders-data.csv`, `order-line-items-data.csv`) keyed by `freshline_order_id` / `freshline_line_item_id`
3. Loads `existing-order-ids.json` and `existing-line-item-ids.json`
4. For each BQ record:
   - If its ID is NOT in `existing-*-ids.json` → it's **new**
   - If its ID IS in `existing-*-ids.json` and fields differ from old CSV → it's **updated**
   - Otherwise → **unchanged**

**Order fields to compare:** state, fulfillment_date, fulfillment_type, net_terms, historical, fulfillment_fee, line_items_count, customer_notes, internal_notes, invoice_notes, opened_at_date, confirmed_at_date, completed_at_date, cancelled_at_date, cc_sales_order_id, qb_invoice_id, backorder_rescheduled, location_name, location_address_line1, location_address_city

> **Note:** `Subtotal`, `Total`, and `Tax` on orders are rollups/formulas in Notion and cannot be set directly — do NOT include them in the diff or update steps. `contact_name` and `contact_email` are also excluded since they're not editable properties in the Orders database.

**Line item fields to compare:** unit_quantity, unit_price, tax, tax_rate, price_rule_type, customer_notes, internal_notes, invoice_notes

> **Note:** On line items, `Subtotal` and `Total` are formulas (computed from unit_price × unit_quantity + tax). `Product name`, `Variant name`, `Variant SKU`, `Variant unit`, `Variant case size`, `Stock cost`, and `Price rule value` do not exist as settable properties in the Notion database — do NOT include them in the diff or update steps.

Normalize values for comparison: treat None/null/"" as equivalent; normalize floats to 2 decimal places.

Output JSON files with the new and updated record sets (including the Notion page_id for updates and list of changed fields).

## Step 3: Create New Orders in Notion

For each new order, use `notion-knoxx` MCP `API-post-page` with parent `{"type": "data_source_id", "data_source_id": "b04f62ec-bb3d-448b-852e-8ac82433bec1"}`.

**Notion property mapping for orders:**
- `Order Title` (title): order_number
- `Freshline order ID` (rich_text): freshline_order_id
- `Freshline customer ID` (rich_text): customer_id
- `Freshline contact ID` (rich_text): contact_id
- `State` (select): state (values: open, confirmed, complete, cancelled, draft)
- `Fulfilment date` (date): fulfillment_date as {start: "YYYY-MM-DD"}
- `Fulfilment type` (select): fulfillment_type (values: delivery, pickup)
- `Net terms (days)` (number): net_terms
- `Historical` (checkbox): historical == "true"
- `Fulfilment fee` (number): fulfillment_fee
- `Line items count` (number): line_items_count
- `Opened at` (date): opened_at_date as {start: "YYYY-MM-DD"} — AEST date, already formatted
- `Confirmed at` (date): confirmed_at_date as {start: "YYYY-MM-DD"} — AEST date, already formatted
- `Completed at` (date): completed_at_date as {start: "YYYY-MM-DD"} — AEST date, already formatted
- `Cancelled at` (date): cancelled_at_date as {start: "YYYY-MM-DD"} — AEST date, already formatted
- `Customer notes` (rich_text): customer_notes
- `Internal notes` (rich_text): internal_notes
- `Invoice notes` (rich_text): invoice_notes
- `CC sales order ID` (rich_text): cc_sales_order_id
- `QB invoice ID` (rich_text): qb_invoice_id
- `Backorder rescheduled` (checkbox): backorder_rescheduled == "true"
- `Freshline location ID` (rich_text): location_id
- `Location name` (rich_text): location_name
- `Location address line 1` (rich_text): location_address_line1
- `Location address line 2` (rich_text): location_address_line2
- `Location city` (rich_text): location_address_city
- `Location region` (rich_text): location_address_region
- `Location region code` (rich_text): location_address_region_code
- `Location postal code` (rich_text): location_address_postal_code
- `Customer` (relation): resolve customer_id via lookup-customers.json → [{id: page_id}]
- `Contact` (relation): resolve contact_email via lookup-contacts.json → [{id: entry.page_id}]

> **Important:** The relation properties are `Customer` and `Contact` (singular), NOT `Customers`/`Contacts`. Do NOT send `Subtotal`, `Total`, or `Tax` — these are rollups/formulas computed from the linked line items.

After creating, add the new freshline_order_id → notion_page_id to existing-order-ids.json.

## Step 4: Create New Line Items in Notion

For each new line item, use `API-post-page` with parent data_source_id `33c8094c-3d8a-8074-a5b3-000bc7dad468`.

**Notion property mapping for line items:**
- `Name` (title): "{variant_sku} — {product_name}"
- `Freshline line item ID` (rich_text): freshline_line_item_id
- `Freshline order ID` (rich_text): order_id
- `Freshline variant ID` (rich_text): variant_id
- `Unit quantity` (number): unit_quantity
- `Unit price` (number): unit_price
- `Tax` (number): tax
- `Tax rate` (number): tax_rate
- `Price rule type` (rich_text): price_rule_type
- `Customer notes` (rich_text): customer_notes
- `Internal notes` (rich_text): internal_notes
- `Invoice notes` (rich_text): invoice_notes
- `Order` (relation): resolve order_id via existing-order-ids.json → [{id: page_id}]
- `Product` (relation): resolve variant_id via lookup-products.json → [{id: page_id}]

> **Important:** Do NOT send `Subtotal` or `Total` (formulas), or `Product name`, `Variant name`, `Variant SKU`, `Variant unit`, `Variant case size`, `Stock cost`, `Price rule value` — these properties do not exist in the Notion database. SKU and Product Unit are rollups populated automatically from the Product relation.

After creating, add the new freshline_line_item_id → notion_page_id to existing-line-item-ids.json.

## Step 5: Update Changed Records in Notion

For each updated order or line item, use `notion-knoxx` MCP `API-patch-page` with the Notion page_id from the existing-*-ids.json maps. Only send the changed properties.

Use the same property mapping as above, but only include fields that actually changed.

For number fields: parse the value to float/int. For date fields (opened_at_date, confirmed_at_date, completed_at_date, cancelled_at_date, fulfillment_date): use `{"date": {"start": "YYYY-MM-DD"}}`. For rich_text: wrap in `[{"type": "text", "text": {"content": value}}]`. For select: `{"name": value}`. For checkbox: boolean.

## Step 6: Update Local CSVs

After all Notion operations complete, overwrite the old CSVs with the fresh BQ data so tomorrow's diff has the correct baseline:
- Save fresh orders to `orders-data.csv`
- Save fresh line items to `order-line-items-data.csv`

## Step 7: Report Summary

Output a concise summary with counts: total orders in BQ, new/updated/unchanged orders, total line items in BQ, new/updated/unchanged line items. If any records were updated, list which order numbers and what fields changed. If there were errors, list them.

Keep the report short — this runs unattended and Dennis will review the output.
