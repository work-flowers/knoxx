-- CREATE OR REPLACE VIEW Zapier.quarterly_forecast_vs_actuals AS

WITH base AS (
  SELECT DISTINCT
    today,
    DATE_SUB(today, INTERVAL 6 MONTH) AS shifted_date  -- aligns fiscal Q1 to calendar Q1
  FROM knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard
),

q AS (
  SELECT
    today,
    shifted_date,
    DATE_TRUNC(shifted_date, QUARTER) AS cur_cal_q_start,
    DATE_SUB(DATE_TRUNC(shifted_date, QUARTER), INTERVAL 3 MONTH) AS prev_cal_q_start
  FROM base
),

dateref AS (
  SELECT
    today,

    -- current fiscal quarter start
    DATE_ADD(cur_cal_q_start, INTERVAL 6 MONTH) AS current_fq_start,

    -- current fiscal quarter end
    DATE_ADD(
      DATE_SUB(
        DATE_ADD(cur_cal_q_start, INTERVAL 3 MONTH),
        INTERVAL 1 DAY
      ),
      INTERVAL 6 MONTH
    ) AS current_fq_end,

    -- prior fiscal quarter start
    DATE_ADD(prev_cal_q_start, INTERVAL 6 MONTH) AS prior_fq_start,

    -- prior fiscal quarter end
    DATE_ADD(
      DATE_SUB(
        DATE_ADD(prev_cal_q_start, INTERVAL 3 MONTH),
        INTERVAL 1 DAY
      ),
      INTERVAL 6 MONTH
    ) AS prior_fq_end
  FROM q
),

actuals AS (
  SELECT
    sd.customerid,
    sd.customername,
    today,
    SUM(CASE WHEN sd.txndate BETWEEN dr.current_fq_start AND dr.current_fq_end THEN sd.amt ELSE 0 END) AS current_quarter_actual,
    SUM(CASE WHEN sd.txndate BETWEEN dr.prior_fq_start AND dr.prior_fq_end THEN sd.amt ELSE 0 END) AS prior_quarter_actual
  FROM `knoxx-foods-451311.Dashboards.Reporting_Sales_Dashboard` AS sd
  CROSS JOIN dateref AS dr
  GROUP BY 1,2,3
)

SELECT * FROM actuals