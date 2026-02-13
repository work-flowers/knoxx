WITH line_items AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_order_line_items
	WHERE order_id = 'ordr_01KH2NVFDQVP7YFA68SJ0VMAQV'
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
)

SELECT *
FROM line_items