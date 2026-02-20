WITH line_items AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_order_line_items
	WHERE order_id = ''
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
)

SELECT 
	li.variant_sku,
	li.variant_unit,
	CAST(li.unit_quantity AS FLOAT64) / COALESCE(conv.Qty_KGs, 1) AS unit_quantity
FROM line_items AS li
LEFT JOIN Carton_Cloud.Stock_Report AS conv
	ON li.variant_sku = conv.SKU
	AND li.variant_unit = 'kilogram'