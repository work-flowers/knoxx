WITH pv AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_product_variants
	QUALIFY ROW_NUMBER() OVER(PARTITION BY product_id ORDER BY updated_at DESC) = 1
),
p AS (
	SELECT *
	FROM Knoxx_Freshline.freshline_products
	QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) = 1
)

SELECT
	pv.id AS variant_id,
	pv.product_id,
	pv.sku,
	pv.case_size,
	pv.unit,
	pv.name AS variant_name,
	p.name AS product_name,
	p.description AS product_desc,
	p.status,
	ARRAY_TO_STRING(p.image_urls, ', ') AS image_urls
FROM pv
INNER JOIN p
	ON pv.product_id = p.id