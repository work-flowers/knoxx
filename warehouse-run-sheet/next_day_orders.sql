WITH orders AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_orders
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY synced_at DESC) = 1
),

line_items AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_order_line_items
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY synced_at DESC) = 1
),

custom_data AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_custom_data
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY synced_at DESC) = 1
),

customers AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_customers
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY synced_at DESC) = 1
)



SELECT 
	o.order_number,
	o.id AS order_id,
	o.customer_id,
	o.state,
	cus.name AS customer_name,
	cd.value AS pallet_status,
	o.internal_notes AS internal_order_notes,
	o.location_address_line1,
	o.location_address_line2,
	o.location_address_line3,
	o.location_address_city,
	o.location_address_region_code,
	o.location_address_country_code,
	o.location_address_postal_code,
	li.variant_name,
	li.variant_sku,
	li.variant_unit,
	li.unit_quantity,
	li.internal_notes AS line_item_notes,
	li.invoice_notes	
FROM orders AS o
LEFT JOIN customers AS cus
	ON o.customer_id = cus.id
LEFT JOIN line_items AS li
	ON o.id = li.order_id
LEFT JOIN custom_data AS cd
	ON o.customer_id = cd.owner_id
	AND cd.key = 'pallet-status'
WHERE
	1 = 1 
	AND o.customer_id NOT IN ('buyr_01K3G5PRDX1T039T5ADTP87YFR')
	AND o.fulfillment_date = DATE_ADD(CURRENT_DATE, INTERVAL 1 DAY)
-- 	AND o.state ='confirmed'