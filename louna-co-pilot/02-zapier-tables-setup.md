# Zapier Tables & Sync Zaps — Setup Guide

This file replaces the former Lookup Agent. Name resolution is now handled directly by the main coordinator agent using Zapier Tables with automatic vector embedding.

---

## 1. Zapier Tables to Create

### Table: Customers

| Column | Type | Source |
|---|---|---|
| `Id` | Number | `Chat_Bot_Customers.Id` |
| `Customer` | Text | `Chat_Bot_Customers.Customer` |

### Table: Products

| Column | Type | Source |
|---|---|---|
| `Id` | Number | `Chat_Bot_Products.Id` |
| `Product` | Text | `Chat_Bot_Products.Product` |

**Notes:**
- Zapier automatically generates vector embeddings on text columns, enabling semantic search.
- The coordinator agent should be granted access to both Tables as knowledge sources.
- Semantic search handles typos, abbreviations, partial names, and pack size variations (e.g. "3x3", "3*3 kg") without explicit fuzzy matching logic.

---

## 2. Sync Zaps

Two Zaps are needed to keep the Tables in sync with the BigQuery source of truth.

### Zap 1: Sync Customers

**Trigger:** Investigate the upstream source of truth for new customers.

- **Option A — Webhook trigger:** If the system that creates new customers (e.g. QuickBooks, CRM) supports webhooks, use a webhook trigger for near-real-time sync.
- **Option B — Schedule trigger:** Poll BigQuery on a schedule (e.g. every 15 minutes) for new or updated rows.

**Action:** Upsert row in the Customers Zapier Table.

- Match on `Id` to avoid duplicates.
- Map `Id` → `Id`, `Customer` → `Customer`.

**BigQuery polling query (if using Option B):**
```sql
SELECT
  CAST(Id AS INT64) AS Id,
  Customer
FROM `Chat_Bot_Customers`
WHERE _PARTITIONTIME IS NULL
   OR _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY Id
```

> Adjust the `INTERVAL` to match your polling frequency with some overlap for safety.

### Zap 2: Sync Products

Same pattern as Customers, targeting `Chat_Bot_Products`.

**BigQuery polling query (if using Option B):**
```sql
SELECT
  CAST(Id AS INT64) AS Id,
  Product
FROM `Chat_Bot_Products`
WHERE _PARTITIONTIME IS NULL
   OR _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY Id
```

---

## 3. Initial Backfill

Before the agent goes live, do a one-time backfill of both Tables from BigQuery.

### Backfill Customers
```sql
SELECT
  CAST(Id AS INT64) AS Id,
  Customer
FROM `Chat_Bot_Customers`
ORDER BY Id
```

### Backfill Products
```sql
SELECT
  CAST(Id AS INT64) AS Id,
  Product
FROM `Chat_Bot_Products`
ORDER BY Id
```

**Method:** Run these queries in BigQuery, export to CSV, and import into the respective Zapier Tables. Alternatively, use a Zap with a manual trigger to pull all rows from BigQuery and create Table records in a loop.

---

## 4. Data Hygiene

The coordinator agent filters out rows where the name contains "staff", "sample", "test", or "misc" at query time. However, you may also want to exclude these at the Table level:

- **Option A:** Add a filter step in the sync Zaps to skip rows matching these patterns before upserting.
- **Option B:** Leave them in the Table and rely on the coordinator's filtering (simpler, but slightly noisier semantic search results).

Recommendation: **Option A** — cleaner Tables produce better vector embeddings.

---

## 5. Agent Configuration

In the Zapier Agent builder:

1. Add both Tables as **knowledge sources** to the main coordinator agent (Louna).
2. The coordinator's system instructions (see `01-main-coordinator-louna.md`) already include the NAME RESOLUTION section describing how to use these Tables.
3. **Do not** add these Tables to the sub-agents — only the coordinator needs them.
4. The sub-agents (Pricing, Invoice History, Logistics) receive resolved IDs from the coordinator and query BigQuery directly.

---

## 6. Monitoring

Set up alerts for:

- **Sync Zap failures** — if either Zap errors, the Tables will go stale.
- **Table row count drift** — periodically compare Table row counts against BigQuery (`SELECT COUNT(*) FROM Chat_Bot_Customers` / `Chat_Bot_Products`). A significant discrepancy indicates missed syncs.
