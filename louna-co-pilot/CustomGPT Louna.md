# app.py

import os, re from fastapi import FastAPI, Header, HTTPException, Query from typing import Optional from google.cloud import bigquery  API\_KEY \= os.getenv("API\_KEY") BQ\_PROJECT \= os.getenv("BQ\_PROJECT") BQ\_DATASET \= os.getenv("BQ\_DATASET")  client \= bigquery.Client(project=BQ\_PROJECT) app \= FastAPI(title="Louna Pricing API (IDs Clean)")  def check\_key(x\_api\_key: Optional\[str\], auth: Optional\[str\]):     ok \= (x\_api\_key and x\_api\_key \== API\_KEY)     if not ok and auth and auth.startswith("Bearer "):         ok \= (auth.split(" ",1)\[1\] \== API\_KEY)     if not ok:         raise HTTPException(status\_code=401, detail="Invalid API key")  def normalize\_pack(s: Optional\[str\]) \-\> str:     if not s: return ""     return re.sub(r"3\\s\*\[\*x\]\\s\*3(\\s\*kg)?", "3x3", s.lower().strip())  def like\_param(product: str, pack: Optional\[str\]) \-\> str:     base \= product.lower().strip()     if pack: base \+= " " \+ normalize\_pack(pack)     base \= re.sub(r"\\s+", " ", base)     return f"%{base}%"  \# \---------- LOOKUPS \---------- @app.get("/customers") def customers(q: str \= Query(...), limit: int \= Query(10, ge=1, le=100),               x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),               authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH toks AS (SELECT SPLIT(REGEXP\_REPLACE(LOWER(@q), r'\[^a-z0-9\]+',' '),' ') AS arr)     SELECT CAST(c.Id AS STRING) AS Id, c.Customer AS Customer,            (SELECT COUNTIF(LOWER(c.Customer) LIKE CONCAT('%',tok,'%')) FROM toks, UNNEST(arr) tok) AS hits,            LOWER(c.Customer)=LOWER(@q) AS exact     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Customers\` c, toks     ORDER BY exact DESC, hits DESC, LENGTH(c.Customer) ASC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("q","STRING",q.lower().strip()),                           bigquery.ScalarQueryParameter("limit","INT64",limit)\]     )).result()\]     return {"ok": True, "rows": rows}  @app.get("/products") def products(q: str \= Query(...), pack: Optional\[str\] \= Query(None), limit: int \= Query(10, ge=1, le=100),              x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),              authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     search\_q \= f"{q} {normalize\_pack(pack)}".strip() if pack else q     sql \= f"""     WITH toks AS (SELECT SPLIT(REGEXP\_REPLACE(LOWER(@q), r'\[^a-z0-9\]+',' '),' ') AS arr)     SELECT CAST(p.Id AS STRING) AS Id, p.Product AS Product,            (SELECT COUNTIF(LOWER(REGEXP\_REPLACE(p.Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3'))                             LIKE CONCAT('%',tok,'%')) FROM toks, UNNEST(arr) tok) AS hits,            LOWER(REGEXP\_REPLACE(p.Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) \= LOWER(@q) AS exact     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\` p, toks     ORDER BY exact DESC, hits DESC, LENGTH(p.Product) ASC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("q","STRING",search\_q.lower().strip()),                           bigquery.ScalarQueryParameter("limit","INT64",limit)\]     )).result()\]     return {"ok": True, "rows": rows}  \# \---------- BY-ID ENDPOINTS \---------- @app.get("/lastinvoice\_byid") def lastinvoice\_byid(customer\_id: str \= Query(...), product\_id: str \= Query(...),                      x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                      authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH c AS (       SELECT LOWER(Customer) AS cname       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Customers\`       WHERE CAST(Id AS STRING) \= CAST(@customer\_id AS STRING)     ),     p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     )     SELECT l.Customer\_Name, l.Product\_Name, l.Unit,            CAST(l.Last\_Invoiced\_Price AS FLOAT64) AS Last\_Invoiced\_Price,            l.Last\_Invoiced\_Date, l.Quoted\_Price\_Per\_QB\_Unit     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Last\_InvoicedvsQuoted\_Price\` l, c, p     WHERE LOWER(l.Customer\_Name) \= c.cname       AND LOWER(REGEXP\_REPLACE(l.Product\_Name, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')     ORDER BY l.Last\_Invoiced\_Date DESC, l.Last\_Invoiced\_Price DESC     LIMIT 1     """     rows \= list(client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("customer\_id","STRING",customer\_id),                           bigquery.ScalarQueryParameter("product\_id","STRING",product\_id)\]     )).result())     if not rows: return {"ok": True, "found": False}     r \= rows\[0\]     return {"ok": True, "found": True, "latest": {         "Customer\_Name": r\["Customer\_Name"\],         "Product\_Name": r\["Product\_Name"\],         "Unit": r\["Unit"\],         "Last\_Invoiced\_Price": float(r\["Last\_Invoiced\_Price"\]),         "Last\_Invoiced\_Date": str(r\["Last\_Invoiced\_Date"\]),         "Quoted\_Price\_Per\_QB\_Unit": float(r\["Quoted\_Price\_Per\_QB\_Unit"\]) if r\["Quoted\_Price\_Per\_QB\_Unit"\] is not None else None     }}  @app.get("/invoiceitems\_byid") def invoiceitems\_byid(customer\_id: str \= Query(...), product\_id: str \= Query(...), limit: int \= Query(10, ge=1, le=100),                       x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                       authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH c AS (       SELECT LOWER(Customer) AS cname       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Customers\`       WHERE CAST(Id AS STRING) \= CAST(@customer\_id AS STRING)     ),     p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     )     SELECT customername, itemname, Invoice, txndate,            CAST(unitprice AS FLOAT64) AS unitprice,            CAST(qty AS FLOAT64) AS qty,            CAST(amt AS FLOAT64) AS amt     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\`, c, p     WHERE LOWER(customername) \= c.cname       AND LOWER(REGEXP\_REPLACE(itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')     ORDER BY txndate DESC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("customer\_id","STRING",customer\_id),                           bigquery.ScalarQueryParameter("product\_id","STRING",product\_id),                           bigquery.ScalarQueryParameter("limit","INT64",limit)\]     )).result()\]     return {"ok": True, "rows": rows}  @app.get("/peerprices\_byid") def peerprices\_byid(product\_id: str \= Query(...),                     x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                     authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     sql\_last3 \= f"""     WITH p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     )     SELECT i.txndate AS date, CAST(i.unitprice AS FLOAT64) AS unit\_price     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\` i, p     WHERE LOWER(REGEXP\_REPLACE(i.itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')     ORDER BY i.txndate DESC     LIMIT 3     """     sql\_med \= f"""     WITH p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     )     SELECT APPROX\_QUANTILES(CAST(i.unitprice AS FLOAT64), 2)\[OFFSET(1)\] AS median     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\` i, p     WHERE LOWER(REGEXP\_REPLACE(i.itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')       AND i.txndate \>= DATE\_SUB(CURRENT\_DATE(), INTERVAL 180 DAY)     """     params \= \[bigquery.ScalarQueryParameter("product\_id","STRING",product\_id)\]     last3 \= \[dict(r) for r in client.query(sql\_last3, job\_config=bigquery.QueryJobConfig(query\_parameters=params)).result()\]     med\_row \= list(client.query(sql\_med, job\_config=bigquery.QueryJobConfig(query\_parameters=params)).result())\[0\]     return {"ok": True, "last3": last3, "median": float(med\_row\["median"\]) if med\_row\["median"\] is not None else None}  @app.get("/costinputs\_byid") def costinputs\_byid(product\_id: str \= Query(...),                     x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                     authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH p AS (       SELECT CAST(@product\_id AS STRING) AS pid,              LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     )     SELECT m.Product, m.Item\_Id, m.QB\_Unit,            CAST(m.LandedCost\_Manual\_QB AS FLOAT64) AS LandedCost\_Manual\_QB,            CAST(m.Recommended\_price\_profit\_percentage AS FLOAT64) AS Recommended\_price\_profit\_percentage,            CAST(m.Min\_price\_Margin\_percentage AS FLOAT64) AS Min\_price\_Margin\_percentage,            m.Costing\_Last\_Updated\_ts,            CAST(m.Maximum\_Quantity\_Per\_Container AS FLOAT64) AS Maximum\_Quantity\_Per\_Container,            CAST(m.Maximum\_Quantity\_Per\_Pallet AS FLOAT64) AS Maximum\_Quantity\_Per\_Pallet     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\_Landed\_Cost\_Final\_Manual\` m, p     WHERE CAST(m.Item\_Id AS STRING) \= p.pid        OR LOWER(REGEXP\_REPLACE(m.Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("product\_id","STRING",product\_id)\]     )).result()\]     return {"ok": True, "rows": rows}  \# \---------- LEGACY (unchanged) \---------- @app.get("/lastinvoice") def lastinvoice(customer: str \= Query(...), product: str \= Query(...), pack: Optional\[str\] \= Query(None),                 x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                 authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     product\_like \= like\_param(product, pack)     sql \= f"""     SELECT Customer\_Name, Product\_Name, Unit,            CAST(Last\_Invoiced\_Price AS FLOAT64) AS Last\_Invoiced\_Price,            Last\_Invoiced\_Date, Quoted\_Price\_Per\_QB\_Unit     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Last\_InvoicedvsQuoted\_Price\`     WHERE LOWER(Customer\_Name)=@customer       AND LOWER(REGEXP\_REPLACE(Product\_Name, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE @product\_like     ORDER BY Last\_Invoiced\_Date DESC, Last\_Invoiced\_Price DESC     LIMIT 1     """     job \= client.query(sql, job\_config=bigquery.QueryJobConfig(query\_parameters=\[         bigquery.ScalarQueryParameter("customer","STRING",customer.lower().strip()),         bigquery.ScalarQueryParameter("product\_like","STRING",product\_like),     \]))     rows \= list(job.result())     if not rows: return {"ok": True, "found": False}     r \= rows\[0\]     return {"ok": True, "found": True, "latest": {         "Customer\_Name": r\["Customer\_Name"\], "Product\_Name": r\["Product\_Name"\], "Unit": r\["Unit"\],         "Last\_Invoiced\_Price": float(r\["Last\_Invoiced\_Price"\]), "Last\_Invoiced\_Date": str(r\["Last\_Invoiced\_Date"\]),         "Quoted\_Price\_Per\_QB\_Unit": float(r\["Quoted\_Price\_Per\_QB\_Unit"\]) if r\["Quoted\_Price\_Per\_QB\_Unit"\] is not None else None     }}  @app.get("/invoiceitems") def invoiceitems(customer: str \= Query(...), product: str \= Query(...), pack: Optional\[str\] \= Query(None),                  limit: int \= Query(10, ge=1, le=100),                  x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                  authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     product\_like \= like\_param(product, pack)     sql \= f"""     SELECT customername, itemname, Invoice, txndate,            CAST(unitprice AS FLOAT64) AS unitprice,            CAST(qty AS FLOAT64) AS qty,            CAST(amt AS FLOAT64) AS amt     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\`     WHERE LOWER(customername)=@customer       AND LOWER(REGEXP\_REPLACE(itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE @product\_like     ORDER BY txndate DESC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[             bigquery.ScalarQueryParameter("customer","STRING",customer.lower().strip()),             bigquery.ScalarQueryParameter("product\_like","STRING",product\_like),             bigquery.ScalarQueryParameter("limit","INT64",limit),         \]     )).result()\]     return {"ok": True, "rows": rows}  @app.get("/peerprices") def peerprices(product: str \= Query(...), pack: Optional\[str\] \= Query(None),                x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     product\_like \= like\_param(product, pack)     sql\_last3 \= f"""     SELECT txndate AS date, CAST(unitprice AS FLOAT64) AS unit\_price     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\`     WHERE LOWER(REGEXP\_REPLACE(itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE @product\_like     ORDER BY txndate DESC     LIMIT 3     """     sql\_med \= f"""     SELECT APPROX\_QUANTILES(CAST(unitprice AS FLOAT64), 2)\[OFFSET(1)\] AS median     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\`     WHERE LOWER(REGEXP\_REPLACE(itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE @product\_like       AND txndate \>= DATE\_SUB(CURRENT\_DATE(), INTERVAL 180 DAY)     """     params \= \[bigquery.ScalarQueryParameter("product\_like","STRING",product\_like)\]     last3 \= \[dict(r) for r in client.query(sql\_last3, job\_config=bigquery.QueryJobConfig(query\_parameters=params)).result()\]     med\_row \= list(client.query(sql\_med, job\_config=bigquery.QueryJobConfig(query\_parameters=params)).result())\[0\]     return {"ok": True, "last3": last3, "median": float(med\_row\["median"\]) if med\_row\["median"\] is not None else None}  @app.get("/costinputs") def costinputs(product: str \= Query(...), pack: Optional\[str\] \= Query(None),                x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                authorization: Optional\[str\] \= Header(None)):     check\_key(x\_api\_key, authorization)     product\_like \= like\_param(product, pack)     sql \= f"""     SELECT Product, Item\_Id, QB\_Unit,            CAST(LandedCost\_Manual\_QB AS FLOAT64) AS LandedCost\_Manual\_QB,            CAST(Recommended\_price\_profit\_percentage AS FLOAT64) AS Recommended\_price\_profit\_percentage,            CAST(Min\_price\_Margin\_percentage AS FLOAT64) AS Min\_price\_Margin\_percentage,            Costing\_Last\_Updated\_ts,            CAST(Maximum\_Quantity\_Per\_Container AS FLOAT64) AS Maximum\_Quantity\_Per\_Container,            CAST(Maximum\_Quantity\_Per\_Pallet AS FLOAT64) AS Maximum\_Quantity\_Per\_Pallet     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\_Landed\_Cost\_Final\_Manual\`     WHERE LOWER(Product) LIKE @product\_like        OR LOWER(QB\_Unit) LIKE @product\_like     """     rows \= \[dict(r) for r in client.query(sql, job\_config=bigquery.QueryJobConfig(         query\_parameters=\[bigquery.ScalarQueryParameter("product\_like","STRING",product\_like)\]     )).result()\]     return {"ok": True, "rows": rows}  @app.get("/invoiceitems\_bycustomer") def invoiceitems\_bycustomer(customer\_id: str \= Query(...),                             months: int \= Query(12, ge=1, le=36),                             limit: int \= Query(200, ge=1, le=1000),                             x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                             authorization: Optional\[str\] \= Header(None)):     """     Customer-wide invoice history across ALL products.     Returns rows in the same shape as /invoiceitems\_byid.     """     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH c AS (       SELECT LOWER(Customer) AS cname       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Customers\`       WHERE CAST(Id AS STRING) \= CAST(@customer\_id AS STRING)     ),     win AS (SELECT DATE\_SUB(CURRENT\_DATE(), INTERVAL @months MONTH) AS start\_dt)     SELECT customername, itemname, Invoice, txndate,            CAST(unitprice AS FLOAT64) AS unitprice,            CAST(qty AS FLOAT64) AS qty,            CAST(amt AS FLOAT64) AS amt     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\` i, c, win     WHERE LOWER(i.customername) \= c.cname       AND i.txndate \>= win.start\_dt     ORDER BY txndate DESC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(         sql,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("customer\_id","STRING",customer\_id),             bigquery.ScalarQueryParameter("months","INT64",months),             bigquery.ScalarQueryParameter("limit","INT64",limit),         \])     ).result()\]     return {"ok": True, "rows": rows}   @app.get("/invoiceitems\_byproduct") def invoiceitems\_byproduct(product\_id: str \= Query(...),                            months: int \= Query(12, ge=1, le=36),                            limit: int \= Query(200, ge=1, le=1000),                            x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                            authorization: Optional\[str\] \= Header(None)):     """     Product-wide invoice history across ALL customers.     Returns rows in the same shape as /invoiceitems\_byid.     """     check\_key(x\_api\_key, authorization)     sql \= f"""     WITH p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     ),     win AS (SELECT DATE\_SUB(CURRENT\_DATE(), INTERVAL @months MONTH) AS start\_dt)     SELECT customername, itemname, Invoice, txndate,            CAST(unitprice AS FLOAT64) AS unitprice,            CAST(qty AS FLOAT64) AS qty,            CAST(amt AS FLOAT64) AS amt     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Invoice\_Line\_Items\` i, p, win     WHERE LOWER(REGEXP\_REPLACE(i.itemname, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')       AND i.txndate \>= win.start\_dt     ORDER BY txndate DESC     LIMIT @limit     """     rows \= \[dict(r) for r in client.query(         sql,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("product\_id","STRING",product\_id),             bigquery.ScalarQueryParameter("months","INT64",months),             bigquery.ScalarQueryParameter("limit","INT64",limit),         \])     ).result()\]     return {"ok": True, "rows": rows}  @app.get("/landedcost\_byid") def landedcost\_byid(product\_id: str \= Query(...),                     limit: int \= Query(3, ge=1, le=20),                     x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                     authorization: Optional\[str\] \= Header(None)):     """     For a given product\_id, fetch the latest N distinct containers from LandedCost     and attach charge breakdowns (by charge\_type) from Pricing\_Charges.     """     check\_key(x\_api\_key, authorization)      sql \= f"""     \-- Find normalized product name for matching on Item\_Name (handles '3\*3' etc.)     WITH p AS (       SELECT LOWER(REGEXP\_REPLACE(Product, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) AS pnorm       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Chat\_Bot\_Products\`       WHERE CAST(Id AS STRING) \= CAST(@product\_id AS STRING)     ),     lc AS (       SELECT container\_number, Shipping\_Agreement, Item\_Id, Item\_Name, Unit\_Name,              CAST(Unit\_Price AS FLOAT64) AS Unit\_Price,              CAST(Landed\_Cost\_Calculated AS FLOAT64) AS Landed\_Cost\_Calculated,              TxnDate       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.LandedCost\`, p       WHERE CAST(Item\_Id AS STRING) \= CAST(@product\_id AS STRING)          OR LOWER(REGEXP\_REPLACE(Item\_Name, r'3\\\\s\*\[\*x\]\\\\s\*3(\\\\s\*kg)?','3x3')) LIKE CONCAT('%', p.pnorm, '%')     ),     \-- De-dup within container and keep latest row per container     latest\_per\_container AS (       SELECT lc.\*,              ROW\_NUMBER() OVER (PARTITION BY container\_number ORDER BY TxnDate DESC) AS rn       FROM lc     ),     topN AS (       SELECT \* FROM latest\_per\_container       WHERE rn \= 1       ORDER BY TxnDate DESC       LIMIT @limit     ),      charges AS (       \-- 1\) pre-aggregate by (container\_number, charge\_type)       WITH agg AS (         SELECT           container\_number,           charge\_type,           SUM(CAST(Amount\_Adjusted AS FLOAT64)) AS amount         FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Pricing\_Charges\`         GROUP BY container\_number, charge\_type       )       \-- 2\) roll up to container level and build an array of (charge\_type, amount)       SELECT         container\_number,         SUM(amount) AS total\_charges,         ARRAY\_AGG(STRUCT(charge\_type, amount) ORDER BY charge\_type) AS charges       FROM agg       GROUP BY container\_number     )     SELECT t.container\_number, t.Shipping\_Agreement, t.Item\_Id, t.Item\_Name, t.Unit\_Name,            t.Unit\_Price, t.Landed\_Cost\_Calculated, t.TxnDate,            c.total\_charges,            c.charges     FROM topN t     LEFT JOIN charges c       USING (container\_number)     ORDER BY t.TxnDate DESC     """     rows \= \[dict(r) for r in client.query(         sql,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("product\_id","STRING",product\_id),             bigquery.ScalarQueryParameter("limit","INT64",limit),         \])     ).result()\]     return {"ok": True, "rows": rows}  @app.get("/container\_cost\_breakdown") def container\_cost\_breakdown(container\_number: str \= Query(...),                              x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),                              authorization: Optional\[str\] \= Header(None)):     """     For a given container\_number, list all products in LandedCost (with unit price and     landed cost), plus a comprehensive charge breakdown from Pricing\_Charges.     """     check\_key(x\_api\_key, authorization)      \# Products & header (shipping agreement)     sql\_items \= f"""     SELECT container\_number, Shipping\_Agreement, Item\_Id, Item\_Name, Unit\_Name,            CAST(Unit\_Price AS FLOAT64) AS Unit\_Price,            CAST(Landed\_Cost\_Calculated AS FLOAT64) AS Landed\_Cost\_Calculated,            TxnDate     FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.LandedCost\`     WHERE container\_number \= @container\_number     ORDER BY TxnDate DESC, Item\_Name     """      \# Charge breakdown (type \+ totals)     sql\_charges \= f"""     WITH agg AS (       SELECT         container\_number,         charge\_type,         SUM(CAST(Amount\_Adjusted AS FLOAT64)) AS amount       FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.Pricing\_Charges\`       WHERE container\_number \= @container\_number       GROUP BY container\_number, charge\_type     )     SELECT       SUM(amount) AS total\_charges,       ARRAY\_AGG(STRUCT(charge\_type, amount) ORDER BY charge\_type) AS charges     FROM agg     """       items \= \[dict(r) for r in client.query(         sql\_items,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("container\_number","STRING",container\_number),         \])     ).result()\]      chg\_row \= list(client.query(         sql\_charges,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("container\_number","STRING",container\_number),         \])     ).result())      charges \= dict(chg\_row\[0\]) if chg\_row else {"total\_charges": 0.0, "charges": \[\]}      \# Pull a single shipping agreement from items (if present)     shipping\_agreement \= None     for r in items:         if r.get("Shipping\_Agreement"):             shipping\_agreement \= r\["Shipping\_Agreement"\]             break      return {         "ok": True,         "container\_number": container\_number,         "shipping\_agreement": shipping\_agreement,         "charges": charges,         "products": items     } \# \===== Shipping Agreement change scan (across ALL products) \=====  @app.get("/shipping\_agreement\_changes\_scan") def shipping\_agreement\_changes\_scan(     months: int \= Query(24, ge=1, le=120, description="Lookback window in months"),     limit: int \= Query(100, ge=1, le=1000, description="Max products to return"),     x\_api\_key: Optional\[str\] \= Header(None, convert\_underscores=False),     authorization: Optional\[str\] \= Header(None), ):     """     Scan the last N months and return products that experienced any Shipping Agreement change,     with summary stats and up to 3 recent change events per product.      Notes:     \- Handles both \`Shipping Agreement\` and \`Shipping\_Agreement\`.     \- One row per product in \`rows\`, with sample change events.     """     check\_key(x\_api\_key, authorization)      sql \= f"""       WITH win AS (   SELECT DATE\_SUB(CURRENT\_DATE(), INTERVAL @months MONTH) AS start\_dt ), lc AS (   SELECT     COALESCE(CAST(Item\_Id AS STRING), LOWER(Item\_Name)) AS pid,  \-- robust partition key     CAST(Item\_Id AS STRING) AS Item\_Id,     Item\_Name,     container\_number,     Shipping\_Agreement,     TxnDate   FROM \`{BQ\_PROJECT}.{BQ\_DATASET}.LandedCost\`, win   WHERE TxnDate \>= win.start\_dt   GROUP BY pid, Item\_Id, Item\_Name, container\_number, Shipping\_Agreement, TxnDate ), ordered AS (   SELECT     pid, Item\_Id, Item\_Name, container\_number, Shipping\_Agreement, TxnDate,     LAG(Shipping\_Agreement) OVER (PARTITION BY pid ORDER BY TxnDate) AS prev\_agreement   FROM lc   GROUP BY pid,Item\_Id, Item\_Name, container\_number, Shipping\_Agreement, TxnDate ), changes AS (   SELECT     pid,     ANY\_VALUE(Item\_Id)   AS Item\_Id,     ANY\_VALUE(Item\_Name) AS Item\_Name,     container\_number,     TxnDate,     prev\_agreement AS from\_agreement,     Shipping\_Agreement AS to\_agreement   FROM ordered   WHERE prev\_agreement IS NOT NULL     AND prev\_agreement \!= Shipping\_Agreement     GROUP BY pid, container\_number, TxnDate, from\_agreement, to\_agreement ), summary AS (   SELECT     pid,     ANY\_VALUE(Item\_Id)   AS Item\_Id,     ANY\_VALUE(Item\_Name) AS Item\_Name,     COUNT(\*)             AS num\_changes,     MAX(TxnDate)         AS last\_change\_date,     ARRAY\_AGG(DISTINCT from\_agreement IGNORE NULLS) AS froms,     ARRAY\_AGG(DISTINCT to\_agreement   IGNORE NULLS) AS tos   FROM changes   GROUP BY pid ), samples AS (   SELECT     pid,     ARRAY\_AGG(STRUCT(container\_number, TxnDate, from\_agreement, to\_agreement)               ORDER BY TxnDate DESC LIMIT 3\) AS sample\_changes   FROM changes   GROUP BY pid ) SELECT   s.Item\_Id,   s.Item\_Name,   s.num\_changes,   s.last\_change\_date,   ARRAY(     SELECT DISTINCT a     FROM UNNEST(ARRAY\_CONCAT(IFNULL(s.froms, \[\]), IFNULL(s.tos, \[\]))) a   ) AS distinct\_agreements,   sa.sample\_changes FROM summary AS s LEFT JOIN samples AS sa ON s.pid \= sa.pid ORDER BY s.last\_change\_date DESC LIMIT @limit """         rows \= \[dict(r) for r in client.query(         sql,         job\_config=bigquery.QueryJobConfig(query\_parameters=\[             bigquery.ScalarQueryParameter("months", "INT64", months),             bigquery.ScalarQueryParameter("limit",  "INT64", limit),         \])     ).result()\]      return {"ok": True, "rows": rows}

# YAML

openapi: 3.1.1  
info:  
  title: Louna Pricing API (IDs-first)  
  version: "1.0.0"  
servers:  
  \- url: https://louna-pricing-api-ids-clean-q3clkrs5wq-ts.a.run.app  
components:  
  securitySchemes:  
    bearerAuth:  
      type: http  
      scheme: bearer  
      bearerFormat: API\_KEY  
  schemas:  
    LookupResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        rows:  
          type: array  
          items:  
            type: object  
            properties:  
              Id: { type: string }  
              Customer: { type: string }  
              hits: { type: integer }  
              exact: { type: boolean }  
    ProductLookupResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        rows:  
          type: array  
          items:  
            type: object  
            properties:  
              Id: { type: string }  
              Product: { type: string }  
              hits: { type: integer }  
              exact: { type: boolean }  
    LastInvoiceResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        found: { type: boolean }  
        latest:  
          type: object  
          nullable: true  
          properties:  
            Customer\_Name: { type: string }  
            Product\_Name: { type: string }  
            Unit: { type: string }  
            Last\_Invoiced\_Price: { type: number, format: float }  
            Last\_Invoiced\_Date: { type: string }  
            Quoted\_Price\_Per\_QB\_Unit: { type: number, format: float, nullable: true }  
    InvoiceItem:  
      type: object  
      properties:  
        customername: { type: string }  
        itemname:     { type: string }  
        Invoice:      { type: string }  
        txndate:      { type: string }  
        unitprice:    { type: number, format: float }  
        qty:          { type: number, format: float }  
        amt:          { type: number, format: float }  
    InvoiceItemsResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        rows:  
          type: array  
          items: { $ref: '\#/components/schemas/InvoiceItem' }  
    PeerPricesResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        last3:  
          type: array  
          items:  
            type: object  
            properties:  
              date: { type: string }  
              unit\_price: { type: number, format: float }  
        median: { type: number, format: float, nullable: true }  
    CostInputsRow:  
      type: object  
      properties:  
        Product: { type: string }  
        Item\_Id: { type: string }  
        QB\_Unit: { type: string }  
        LandedCost\_Manual\_QB: { type: number, format: float, nullable: true }  
        Recommended\_price\_profit\_percentage: { type: number, format: float, nullable: true }  
        Min\_price\_Margin\_percentage: { type: number, format: float, nullable: true }  
        Costing\_Last\_Updated\_ts: { type: string, nullable: true }  
        Maximum\_Quantity\_Per\_Container: { type: number, format: float, nullable: true }  
        Maximum\_Quantity\_Per\_Pallet: { type: number, format: float, nullable: true }  
    CostInputsResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        rows:  
          type: array  
          items: { $ref: '\#/components/schemas/CostInputsRow' }

    \# \-------- NEW SCHEMAS \--------  
    ChargeBreakdownItem:  
      type: object  
      properties:  
        charge\_type: { type: string }  
        amount:      { type: number, format: float }  
    ChargeBreakdown:  
      type: object  
      properties:  
        total\_charges: { type: number, format: float, nullable: true }  
        charges:  
          type: array  
          items: { $ref: '\#/components/schemas/ChargeBreakdownItem' }

    LandedCostRow:  
      type: object  
      properties:  
        container\_number:        { type: string }  
        Shipping\_Agreement:      { type: string, nullable: true }  
        Item\_Id:                 { type: string }  
        Item\_Name:               { type: string }  
        Unit\_Name:               { type: string }  
        Unit\_Price:              { type: number, format: float }  
        Landed\_Cost\_Calculated:  { type: number, format: float }  
        TxnDate:                 { type: string }  
        total\_charges:           { type: number, format: float, nullable: true }  
        charges:  
          type: array  
          items: { $ref: '\#/components/schemas/ChargeBreakdownItem' }

    LandedCostByIdResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        rows:  
          type: array  
          items: { $ref: '\#/components/schemas/LandedCostRow' }

    ContainerProductRow:  
      type: object  
      properties:  
        container\_number:        { type: string }  
        Shipping\_Agreement:      { type: string, nullable: true }  
        Item\_Id:                 { type: string }  
        Item\_Name:               { type: string }  
        Unit\_Name:               { type: string }  
        Unit\_Price:              { type: number, format: float }  
        Landed\_Cost\_Calculated:  { type: number, format: float }  
        TxnDate:                 { type: string }

    ContainerCostBreakdownResponse:  
      type: object  
      properties:  
        ok: { type: boolean }  
        container\_number:   { type: string }  
        shipping\_agreement: { type: string, nullable: true }  
        charges:            { $ref: '\#/components/schemas/ChargeBreakdown' }  
        products:  
          type: array  
          items: { $ref: '\#/components/schemas/ContainerProductRow' }  
    ShippingAgreementChangeSample:  
      type: object  
      properties:  
        container\_number: { type: string }  
        TxnDate:          { type: string }  
        from\_agreement:   { type: string, nullable: true }  
        to\_agreement:     { type: string, nullable: true }

    ShippingAgreementChangesScanRow:  
      type: object  
      properties:  
        Item\_Id:             { type: string }  
        Item\_Name:           { type: string }  
        num\_changes:         { type: integer }  
        last\_change\_date:    { type: string }  
        distinct\_agreements:  
          type: array  
          items: { type: string }  
        sample\_changes:  
          type: array  
          items: { $ref: '\#/components/schemas/ShippingAgreementChangeSample' }

    ShippingAgreementChangesScanResponse:  
      type: object  
      properties:  
        ok:   { type: boolean }  
        rows:  
          type: array  
          items: { $ref: '\#/components/schemas/ShippingAgreementChangesScanRow' }

security:  
  \- bearerAuth: \[\]

paths:  
  /customers:  
    get:  
      operationId: getCustomers  
      summary: Fuzzy customer lookup → IDs  
      parameters:  
        \- { name: q, in: query, required: true,  schema: { type: string } }  
        \- { name: limit, in: query, required: false, schema: { type: integer, minimum: 1, maximum: 100, default: 10 } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/LookupResponse' }}}}  
  /products:  
    get:  
      operationId: getProducts  
      summary: Fuzzy product lookup → IDs (handles 3x3 pack normalization)  
      parameters:  
        \- { name: q, in: query, required: true,  schema: { type: string } }  
        \- { name: pack, in: query, required: false, schema: { type: string } }  
        \- { name: limit, in: query, required: false, schema: { type: integer, minimum: 1, maximum: 100, default: 10 } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/ProductLookupResponse' }}}}  
  /lastinvoice\_byid:  
    get:  
      operationId: getLastInvoiceById  
      summary: Latest invoiced price (ID-based)  
      parameters:  
        \- { name: customer\_id, in: query, required: true, schema: { type: string } }  
        \- { name: product\_id,  in: query, required: true, schema: { type: string } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/LastInvoiceResponse' }}}}  
  /invoiceitems\_byid:  
    get:  
      operationId: getInvoiceItemsById  
      summary: Recent invoice items (ID-based)  
      parameters:  
        \- { name: customer\_id, in: query, required: true, schema: { type: string } }  
        \- { name: product\_id,  in: query, required: true, schema: { type: string } }  
        \- { name: limit,       in: query, required: false, schema: { type: integer, minimum: 1, maximum: 100, default: 10 } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/InvoiceItemsResponse' }}}}  
  /peerprices\_byid:  
    get:  
      operationId: getPeerPricesById  
      summary: Peer prices (ID-based)  
      parameters:  
        \- { name: product\_id, in: query, required: true, schema: { type: string } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/PeerPricesResponse' }}}}  
  /costinputs\_byid:  
    get:  
      operationId: getCostInputsById  
      summary: Cost inputs (ID-based)  
      parameters:  
        \- { name: product\_id, in: query, required: true, schema: { type: string } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/CostInputsResponse' }}}}  
  /invoiceitems\_bycustomer:  
    get:  
      operationId: getInvoiceItemsByCustomer  
      summary: Recent invoice items for a customer (all products)  
      parameters:  
        \- { name: customer\_id, in: query, required: true, schema: { type: string } }  
        \- { name: months, in: query, required: false, schema: { type: integer, minimum: 1, maximum: 36, default: 12 } }  
        \- { name: limit,  in: query, required: false, schema: { type: integer, minimum: 1, maximum: 1000, default: 200 } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/InvoiceItemsResponse' }}}}  
  /invoiceitems\_byproduct:  
    get:  
      operationId: getInvoiceItemsByProduct  
      summary: Recent invoice items for a product (all customers)  
      parameters:  
        \- { name: product\_id, in: query, required: true, schema: { type: string } }  
        \- { name: months, in: query, required: false, schema: { type: integer, minimum: 1, maximum: 36, default: 12 } }  
        \- { name: limit,  in: query, required: false, schema: { type: integer, minimum: 1, maximum: 1000, default: 200 } }  
      responses:  
        "200": { description: OK, content: { application/json: { schema: { $ref: '\#/components/schemas/InvoiceItemsResponse' }}}}

  \# \-------- NEW PATHS \--------  
  /landedcost\_byid:  
    get:  
      operationId: getLandedCostById  
      summary: Latest N containers for a product with charge breakdown (ID-based)  
      parameters:  
        \- { name: product\_id, in: query, required: true, schema: { type: string } }  
        \- { name: limit,      in: query, required: false, schema: { type: integer, minimum: 1, maximum: 20, default: 3 } }  
      responses:  
        "200":  
          description: OK  
          content:  
            application/json:  
              schema: { $ref: '\#/components/schemas/LandedCostByIdResponse' }

  /container\_cost\_breakdown:  
    get:  
      operationId: getContainerCostBreakdown  
      summary: Per-container cost breakdown (all products \+ charges)  
      parameters:  
        \- { name: container\_number, in: query, required: true, schema: { type: string } }  
      responses:  
        "200":  
          description: OK  
          content:  
            application/json:  
              schema: { $ref: '\#/components/schemas/ContainerCostBreakdownResponse' }  
  /shipping\_agreement\_changes\_scan:  
    get:  
      operationId: getShippingAgreementChangesScan  
      summary: List products that experienced any Shipping Agreement change (global scan)  
      parameters:  
        \- name: months  
          in: query  
          required: false  
          schema: { type: integer, minimum: 1, maximum: 120, default: 24 }  
          description: Lookback window in months  
        \- name: limit  
          in: query  
          required: false  
          schema: { type: integer, minimum: 1, maximum: 1000, default: 100 }  
          description: Max number of products returned  
      responses:  
        "200":  
          description: OK  
          content:  
            application/json:  
              schema: { $ref: '\#/components/schemas/ShippingAgreementChangesScanResponse' }

# Instructions

LOUNA – KNOXX FOODS SALES GPT  
ROLE & MISSION  
You are Louna, Knoxx Foods’ Senior Sales Manager — pragmatic, profit-focused, supportive.  
 Guide reps on pricing, negotiation, landed cost, and next actions without guessing.

DATA ACCESS (STRICT)  
Use only Cloud Run API actions — no web or external lookups.  
 If a call returns no rows →  
“No match found in the database. Try a different spelling or product name.”  
Never fabricate names, IDs, invoices, prices, or peer data.  
 Echo database values exactly.

VOICE & STYLE  
Professional, calm, concise. One question per turn.  
 Encourage (“Excellent”, “Got it”), never overload or sound robotic.  
 Don’t ask for a “price in mind” before fetching data.

API ACTIONS  
Core  
/customers → fuzzy customer lookup → IDs

/products → fuzzy product lookup → IDs (pack optional)

/lastinvoice\_byid → latest invoiced price (customer+product)

/invoiceitems\_byid → invoice lines (customer+product)

/peerprices\_byid → peer summary (last3, median)

/costinputs\_byid → RSP, floor %, QB\_Unit, costing meta

/invoiceitems\_bycustomer → invoices for customer

/invoiceitems\_byproduct → invoices for product

New  
/landedcost\_byid → Product-level landed cost

/container\_cost\_breakdown → Container charge details

/shipping\_agreement\_changes\_scan → Detect CIF↔FOB changes

ID LOOKUP (REQUIRED FIRST)  
Ask one entity at a time: customer, then product (+pack/unit).  
 Use:  
/customers?q=\<text\>\&limit=10  
/products?q=\<text\>\&limit=10\[\&pack=…\]  
Filter: drop rows with staff/sample/test/misc; rank by token match & hits.  
 If unclear → “No strong matches found.”  
 Confirm and persist: customer\_id, product\_id, QB\_Unit, pack.

CORE PRICING FLOW  
1️⃣ Basics: Confirm IDs, collect delivery location, volume.  
 2️⃣ Recommend Price:  
/costinputs\_byid?product\_id=\<\>

Use Recommended\_price\_profit\_percentage as RSP.

Reply: “Recommended: $Y.YY / \<QB\_Unit\> Ex-WH (from RSP). Prices are Ex-WH; delivery charges depend on location.”

Ask: “View peer pricing before deciding?”

3️⃣ If peer opt-in:  
/invoiceitems\_byproduct?product\_id=\<\> (12m)

/peerprices\_byid?product\_id=\<\>

/lastinvoice\_byid?customer\_id=\<\> & product\_id=\<\> (optional)  
 Show median \+ 3 recent peers → “Able to sell at $Y.YY / \<QB\_Unit\> Ex-WH?”

4️⃣ If skip peers:  
No peer data; ask same pricing question.

5️⃣ If pushback:  
 Offer peers if not yet shown.  
 Qualify: competition, volume, delivery, payment.  
 Suggest structure before discounts.  
6️⃣ Positioning:  
“At $Y.YY with monthly volume N, we maintain margin.  
 If they commit to volume or bundle, sharper pricing can be explored.”  
7️⃣ Guardrail:  
 If below Min\_price\_Margin\_percentage:  
“Below minimum profit requires CEO escalation.”

LANDED COST INSIGHTS  
If user asks landed cost or container charges:  
/landedcost\_byid?product\_id=\<\>\&container\_number=\<\>  
Show: Landed cost, container, key charge types.  
 If detail asked →  
/container\_cost\_breakdown?container\_number=\<\>  
Summarize 2-3 top charges (Sea Freight, Wharf, Unloading).  
 If missing context → ask:  
“Which container should I reference?”  
Example:  
“For Product X (CMAU026858), Landed Cost $33.94 driven by Sea Freight $1,350, Unloading $270, Wharf $200 (CIF).”

SHIPPING AGREEMENT CHANGE SCAN  
Triggered by:  
 “Which products changed from CIF to FOB?”  
 “Show shipping agreement changes.”  
 Use:  
/shipping\_agreement\_changes\_scan?months=24\&limit=50  
Show:  
Product name

of changes

Last change date

Old→new agreement types

“In past 24 m, Knoxx Tomato Paste 3 KG switched twice, last in Dec 2024 (CIF→FOB).”

OTHER FUNCTIONS  
Price List:  
“Full catalog not available; I can fetch RSPs by keyword.”  
 /products?q=\<term\> \+ /costinputs\_byid  
Order History:  
 Default \= 12 m (can extend 24 m).  
 Use \_bycustomer, \_byproduct, or \_byid.  
 Show avg Qty/month, last price, brief trend, or table (Date | Qty | Price).

PRINCIPLES  
Profit % \= (Selling − Cost)/Cost ≥ 15%.  
 Use volume/bundles/pickup before discount.  
 Keep cost floors internal.  
 Never invent or guess.

MEMORY  
Persist:  
 customer\_id, product\_id, QB\_Unit, pack, delivery\_location, volume, and flags (peer\_opt\_in, competitive\_deal, etc.)

ERROR HANDLING  
If any call fails:  
“No data found. Check spelling, adjust range, or confirm pack/unit.”  
 Never fabricate or merge unrelated data.

CALL ORDER  
/customers?q=\<text\>\&limit=5

/products?q=\<text\>\&limit=5

/costinputs\_byid?product\_id=\<\>

Peer or invoice (if opted):  
 /invoiceitems\_byproduct, /peerprices\_byid, /lastinvoice\_byid

Cost or logistics:  
 /landedcost\_byid, /container\_cost\_breakdown, /shipping\_agreement\_changes\_scan

CONVERSATIONAL FLOW & GUARDRAILS  
One intent per turn: price | peer | landed | agreement.

Confirm IDs before any API call.

If repeated “check again” → confirm refresh or spelling.

If 0 results → specify which entity failed.

Never “guess” future prices.

If 2 failed attempts → “Let’s verify the product/container before retrying.”

Hierarchy: pricing \> peers \> landed \> agreement.

If user pushes below margin → flag escalation.

If frustration detected → calmly reset:

 “Let’s confirm the product again — I’ll fetch it cleanly.”

Flow:  
Confirm IDs →

Detect intent →

Call API →

Summarize in ≤ 3 bullets →

Ask 1 next question.  
