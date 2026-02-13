WITH line_items AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_order_line_items
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
	WHERE order_id = ''
)

SELECT *
FROM line_items