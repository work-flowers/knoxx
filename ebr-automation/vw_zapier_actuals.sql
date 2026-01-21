CREATE OR REPLACE VIEW Zapier.actuals AS

WITH dateref AS (  
    SELECT DISTINCT
      today,
      -- Curreent fiscal year
      CASE
        WHEN EXTRACT(MONTH FROM today) >= 7 THEN EXTRACT(YEAR FROM today) + 1
        ELSE EXTRACT(YEAR FROM today)
        END AS current_fiscal_year,

      -- Current fiscal quarter
      CASE
        WHEN EXTRACT(MONTH FROM today) BETWEEN 7 AND 9 THEN 1
        WHEN EXTRACT(MONTH FROM today) BETWEEN 10 AND 12 THEN 2
        WHEN EXTRACT(MONTH FROM today) BETWEEN 1 AND 3 THEN 3
        WHEN EXTRACT(MONTH FROM today) BETWEEN 4 AND 6 THEN 4
        END AS current_fiscal_quarter,

      -- Prior fiscal quarter 
      CASE
        WHEN EXTRACT(MONTH FROM today) BETWEEN 7 AND 9 THEN 4
        WHEN EXTRACT(MONTH FROM today) BETWEEN 10 AND 12 THEN 1
        WHEN EXTRACT(MONTH FROM today) BETWEEN 1 AND 3 THEN 2
        WHEN EXTRACT(MONTH FROM today) BETWEEN 4 AND 6 THEN 3
        END AS prior_fiscal_quarter,

      -- Prior fiscal year
      CASE
        WHEN EXTRACT(MONTH FROM today) BETWEEN 7 AND 9 THEN EXTRACT(YEAR FROM today) -- Q1 → prior FY is the current calendar year
        WHEN EXTRACT(MONTH FROM today) BETWEEN 10 AND 12 THEN EXTRACT(YEAR FROM today) -- Q2 → prior FY same as above
        WHEN EXTRACT(MONTH FROM today) BETWEEN 1 AND 6 THEN EXTRACT(YEAR FROM today) - 1 -- Q3/Q4 → prior FY is prior calendar year
        END AS prior_fiscal_year
  FROM `knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard`
)

SELECT
  sd.customerid,
  sd.customername,
  SUM(CASE WHEN sd.txndatefy = dr.current_fiscal_year AND sd.txndatefqtr = dr.current_fiscal_quarter THEN sd.amt ELSE 0 END) AS current_quarter_actual,
  SUM(CASE WHEN sd.txndatefy = dr.prior_fiscal_year AND sd.txndatefqtr = dr.prior_fiscal_quarter THEN sd.amt ELSE 0 END) AS prior_quarter_actual
FROM `knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard` AS sd
CROSS JOIN dateref AS dr
GROUP BY 1,2;