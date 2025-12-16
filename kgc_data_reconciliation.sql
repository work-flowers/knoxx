SELECT
	fe.customername,
	CASE WHEN 
		fe.itemname LIKE 'Coconoxx Coconut Cream%' THEN 'Coconoxx Coconut Cream 20kg'
		ELSE itemname END AS itemname,
	CASE 
		WHEN fe.forecast_month BETWEEN '2025-07-01' AND '2025-09-30' THEN '2025-09-30' 
		WHEN fe.forecast_month BETWEEN '2025-03-01' AND '2025-06-30' THEN '2025-06-30'
		END AS period,
	'forecast' AS type,
	SUM(fe.forecast_qtykg) AS amount
FROM `Forecast`.`Forecast-EBR` AS fe
WHERE 
	customer_id = '156'
	AND fe.forecast_month BETWEEN'2025-03-01' AND '2025-09-30'
GROUP BY 1,2,3,4

UNION ALL

SELECT
    sd.customername,
    CASE WHEN 
		sd.itemname LIKE 'Coconoxx Coconut Cream%' THEN 'Coconoxx Coconut Cream 20kg'
		ELSE itemname END AS itemname,
    CASE 
    	WHEN sd.txndate BETWEEN '2025-07-01' AND '2025-09-30' THEN '2025-09-30'
		WHEN sd.txndate BETWEEN '2025-03-01' AND '2025-06-30' THEN '2025-06-30'
		END AS period,
	'actual' AS type,
	SUM(sd.qtykg) AS amount
  FROM `knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard` AS sd
WHERE 
	customerid = '156'
	AND qtykg > 0
	AND sd.txndate BETWEEN'2025-03-01' AND '2025-09-30'
GROUP BY 1,2,3,4
