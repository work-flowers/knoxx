WITH sales_order AS (
	SELECT
		owner_id AS order_id,
	  	JSON_VALUE(value, '$.sales_order.id')   AS sales_order_id,
  		JSON_VALUE(value, '$.sales_order.uuid') AS sales_order_uuid
	FROM Knoxx_Freshline.freshline_custom_data
	WHERE 
		key = 'carton-cloud-sales-order-id'
		AND COALESCE(JSON_VALUE(value, '$.sales_order.id'), JSON_VALUE(value, '$.sales_order.uuid')) IS NOT NULL
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
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

)

SELECT 
	o.id AS order_id,
	o.order_number,
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
	o.location_address_line3,
	o.location_address_line2,
	o.location_address_line1,
	o.internal_notes,
	o.invoice_notes,
	o.customer_notes,
	COALESCE(o.contact_name, cus.billing_contact_name, cus.name) AS contact_name,
	COALESCE(o.contact_email, cus.billing_contact_email) AS contact_email
FROM orders AS o 
LEFT JOIN sales_order AS so
	ON o.id = so.order_id
LEFT JOIN customers AS cus
	ON o.customer_id = cus.id
WHERE
	1 = 1
	AND o.state NOT IN('cancelled', 'draft', 'complete')
	AND DATE_SUB(o.fulfillment_date, INTERVAL 7 DAY) <= CURRENT_DATE
	AND o.fulfillment_date >= CURRENT_DATE -- remove this filter once state sync issue is resolved
	AND so.order_id IS NULL