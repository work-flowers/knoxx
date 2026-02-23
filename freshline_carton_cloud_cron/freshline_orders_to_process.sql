WITH sales_order AS (
	SELECT
		owner_id AS order_id,
	  	JSON_VALUE(value, '$.sales_order.id')   AS sales_order_id,
  		JSON_VALUE(value, '$.sales_order.uuid') AS sales_order_uuid
	FROM Knoxx_Freshline.freshline_custom_data
	WHERE 
		key = 'carton-cloud-sales-order-id'
	QUALIFY ROW_NUMBER() OVER(PARTITION BY owner_id ORDER BY updated_at DESC) = 1
),

orders AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_orders
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1

),

customers AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_customers
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1

),

chep AS (
	SELECT
		owner_id AS customer_id,
		JSON_VALUE(value) AS chep_status
	FROM Knoxx_Freshline.freshline_custom_data
	WHERE 
		key = 'pallet-status'
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
)

SELECT 
	o.id AS order_id,
	o.order_number,
	cus.name AS customer_name,
	o.state,
	o.fulfillment_date,
	o.fulfillment_type,
	o.customer_id,
	o.contact_id,
	o.location_name,
	o.location_address_country_code,
	o.location_address_region_code,
	o.location_address_city,
	o.location_address_postal_code,
	o.location_address_line1,
	o.location_address_line2,
	o.location_address_line3,
	o.internal_notes,
	o.invoice_notes,
	o.customer_notes,
	chep.chep_status,
	COALESCE(o.contact_name, cus.billing_contact_name, cus.name) AS contact_name,
	COALESCE(o.contact_email, cus.billing_contact_email) AS contact_email
FROM orders AS o 
LEFT JOIN sales_order AS so
	ON o.id = so.order_id
	AND so.sales_order_id IS NOT NULL
LEFT JOIN customers AS cus
	ON o.customer_id = cus.id
LEFT JOIN chep
	USING(customer_id)
WHERE
	1 = 1
	AND o.state = 'confirmed'
	AND DATE_SUB(o.fulfillment_date, INTERVAL 1 DAY) <= CURRENT_DATE
	AND o.fulfillment_date >= CURRENT_DATE
	AND so.order_id IS NULL