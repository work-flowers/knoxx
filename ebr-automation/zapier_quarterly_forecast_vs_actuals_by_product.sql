WITH dateref AS (
  SELECT
	DATE_TRUNC('2025-12-31', QUARTER) AS current_quarter_start,
	DATE_SUB(DATE_ADD(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 QUARTER), INTERVAL 1 DAY) AS current_quarter_end,
	DATE_SUB(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 QUARTER) AS prior_quarter_start,
	DATE_SUB(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 DAY) AS prior_quarter_end,
	CONCAT(
    	FORMAT_DATE('%b', DATE_TRUNC('2025-12-31', QUARTER)),
    	' - ',
    	FORMAT_DATE('%b', DATE_SUB(DATE_ADD(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 QUARTER), INTERVAL 1 DAY)),
    	" '",
    	FORMAT_DATE('%y', DATE_TRUNC('2025-12-31', QUARTER))
  	) AS current_quarter_label,
	
	CONCAT(
		FORMAT_DATE('%b', DATE_SUB(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 QUARTER)),
    	' - ',
	    FORMAT_DATE('%b', DATE_SUB(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 DAY)),
	    " '",
	    FORMAT_DATE('%y', DATE_SUB(DATE_TRUNC('2025-12-31', QUARTER), INTERVAL 1 QUARTER))
    ) AS prior_quarter_label
),

actuals AS (
  SELECT
    sd.customerid,
    sd.customername,
    sd.itemname,
    dr.current_quarter_label,
    dr.prior_quarter_label,
    SUM(CASE WHEN sd.txndate BETWEEN dr.current_quarter_start AND dr.current_quarter_end THEN sd.qtykg ELSE 0 END) AS current_quarter_actual_qtykg,
    SUM(CASE WHEN sd.txndate BETWEEN dr.prior_quarter_start AND dr.prior_quarter_end THEN sd.qtykg ELSE 0 END) AS prior_quarter_actual_qtykg
  FROM `knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard` AS sd
  CROSS JOIN dateref AS dr
  GROUP BY 1,2,3,4,5
),

forecasts AS (
	SELECT
		fe.customer_id AS customerid,
		fe.customername,
		fe.itemname,
		dr.current_quarter_label,
    	dr.prior_quarter_label,
		SUM(CASE WHEN fe.forecast_month BETWEEN dr.current_quarter_start AND dr.current_quarter_end THEN fe.forecast_qtykg ELSE 0 END) AS current_quarter_forecast_qtykg,
		SUM(CASE WHEN fe.forecast_month BETWEEN dr.prior_quarter_start AND dr.prior_quarter_end THEN fe.forecast_qtykg ELSE 0 END) AS prior_quarter_forecast_qtykg
	FROM `Forecast`.`Forecast-EBR` AS fe
	CROSS JOIN dateref AS dr
	GROUP BY 1,2,3,4,5
),

joined AS (
	SELECT 
		COALESCE(a.customerid, f.customerid) AS customerid,
		COALESCE(a.customername, f.customername) AS customername,
		COALESCE(a.itemname, f.itemname) AS itemname,
		COALESCE(a.current_quarter_label, f.current_quarter_label) AS current_quarter_label,
		COALESCE(a.prior_quarter_label, f.prior_quarter_label) AS prior_quarter_label,
		COALESCE(a.current_quarter_actual_qtykg, 0) AS current_quarter_actual_qtykg,
		COALESCE(a.prior_quarter_actual_qtykg, 0) AS prior_quarter_actual_qtykg,
		COALESCE(f.current_quarter_forecast_qtykg, 0) AS current_quarter_forecast_qtykg,
		COALESCE(f.prior_quarter_forecast_qtykg, 0) AS prior_quarter_forecast_qtykg
	
	FROM actuals AS a
	FULL OUTER JOIN forecasts AS f
		USING (customerid, itemname)
)

SELECT * FROM joined
WHERE 
	1 = 1
	AND customerid = '147'
	AND current_quarter_actual_qtykg + prior_quarter_actual_qtykg + current_quarter_forecast_qtykg + prior_quarter_forecast_qtykg > 0