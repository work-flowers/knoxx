# Freshline → Notion Migration Plan

**KF-169** | Draft: 30 March 2026 | Author: Dennis Chiuten
**Hard deadline:** 1 July 2026 (FL renewal avoidance)

---

## 1. Current State: What Lives in Freshline Today

### Data Model (8 tables in `Knoxx_Freshline`)

> **Note:** These tables are **versioned history tables** — Freshline's native BigQuery integration appends a new row each time a record is synced, rather than updating in place. The "Total Rows" column includes all versions; "Unique Records" is the deduplicated count (latest version per `id`). Any queries or migration scripts must deduplicate by taking the most recent `synced_at` per `id`.

| Table | Total Rows | Unique Records | Avg Versions | Description |
|---|---|---|---|---|
| `freshline_customers` | 98 | 98 | 1.0× | Customer accounts (billing address, net terms, status) |
| `freshline_contacts` | 192 | 185 | 1.0× | Contact records linked to customers (name, email, phone, role) |
| `freshline_orders` | 3,252 | 987 | 3.3× | Orders partitioned by `fulfillment_date`, clustered by `customer_id` |
| `freshline_order_line_items` | 6,180 | 1,919 | 3.2× | Line items with product/variant, pricing, quantity, tax |
| `freshline_order_fee_items` | 180 | 56 | 3.2× | Delivery fees, surcharges, percentage-based fees per order |
| `freshline_products` | 128 | 105 | 1.2× | Product catalogue (name, description, handle, images, tax code) |
| `freshline_product_variants` | 113 | 107 | 1.1× | Variants with SKU, case size, unit, lead days, vendor |
| `freshline_custom_data` | 628 | 570 | 1.1× | Key-value store for integration metadata (see below) |

The heaviest versioning is on orders, line items, and fee items (~3× multiplier) — these records change state multiple times (opened → confirmed → completed) and each state change produces a new version row.

### Custom Data Fields (Integration Glue)

These are critical — they're how FL currently links to other systems. The `type` column in `freshline_custom_data` tells us which object each field lives on. In the Notion migration, each becomes a native database property on the corresponding database.

**On Customer** (82–36 unique records per field)

| Key | Records | Notion Property | Purpose |
|---|---|---|---|
| `quickbooksonline_customer_id` | 82 | `qb_customer_id` on Customers DB | Links customer to QB |
| `pallet-status` | 36 | `pallet_status` (select) on Customers DB | CHEP/Loscam pallet defaults |
| `delivery-method` | 33 | `delivery_method` (select) on Customers DB | Default delivery method |
| `delivery-timing` | 22 | `delivery_timing` (select) on Customers DB | Default delivery timing |
| `notes` | 5 | `custom_notes` (text) on Customers DB | Free-text notes |

**On Order** (274–3 unique records per field)

| Key | Records | Notion Property | Purpose |
|---|---|---|---|
| `quickbooksonline_invoice_id` | 274 | `qb_invoice_id` on Orders DB | Links order to QB invoice |
| `carton-cloud-sales-order-id` | 100 | `cc_sales_order_id` on Orders DB | Links order to CC sales order |
| `backorder-rescheduled` | 3 | `backorder_rescheduled` (checkbox) on Orders DB | Backorder tracking |

**On Product Variant** (6 records)

| Key | Records | Notion Property | Purpose |
|---|---|---|---|
| `quickbooksonline_item_id` | 6 | `qb_item_id` on Product Variants DB | Links variant to QB item |

**On Contact** (5–1 records)

| Key | Records | Notion Property | Purpose |
|---|---|---|---|
| `quickbooksonline_customer_id` | 5 | `qb_customer_id` on Contacts DB | Links contact to QB customer |
| `notes` | 1 | `custom_notes` (text) on Contacts DB | Free-text notes |

### Customer × SKU Pricing (Not in BigQuery)

Freshline maintains a **customer-specific price list** (customer × product variant → unit price) that is **not synced to BigQuery**. The BQ line items table records the price at time of order (`price_rule_type` = `fixed_dollar`, `price_rule_value` = the dollar amount), but the master price list — including prices for products a customer is set up for but hasn't ordered recently — only exists in Freshline.

**This data must be extracted directly from Freshline before decommissioning.** It cannot be reliably reconstructed from BQ order history alone.

In Notion, this becomes a **Customer Pricing** database — a junction table relating Customer × Product Variant with a `unit_price` property. When a line item is created against an order, a Zapier automation looks up the price from this table and populates the line item's unit price (which can still be overridden per-order if needed).

---

## 2. Volume Reality Check

Once deduplicated (latest version per ID), the actual volumes align with the ~100 orders/month estimate from the meeting:

| Month | Unique Orders | Unique Line Items | Avg Items/Order |
|---|---|---|---|
| 2025-07 | 38 | 75 | 2.0 |
| 2025-08 | 112 | 237 | 2.1 |
| 2025-09 | 118 | 251 | 2.1 |
| 2025-10 | 126 | 250 | 2.0 |
| 2025-11 | 116 | 215 | 1.9 |
| 2025-12 | 113 | 204 | 1.8 |
| 2026-01 | 111 | 196 | 1.8 |
| 2026-02 | 117 | 232 | 2.0 |
| 2026-03 | 128 | 245 | 1.9 |

Steady state is **~115 orders/month** with **~230 line items/month** (averaging ~2 items per order). At this volume Notion databases will comfortably handle day-to-day operations.

### Version History: What We Lose in the Migration

Freshline's ETL into BigQuery preserves a full version history of every record (via append-only sync). This gives Knoxx the ability to query how an order changed over time — e.g. when it moved from "opened" to "confirmed", what the original line items were before edits, etc.

**Notion does not expose version history via API.** Notion maintains page-level version history in its UI (visible under "Page history"), but this is:

- Not queryable via the Notion API
- Not available to Zapier or any automation tool
- Not structured — it's a diff of the entire page, not field-level change tracking

**Implications:**

1. **Audit trail:** If Knoxx needs a structured audit trail of order changes (e.g. for compliance, dispute resolution, or debugging), we need to build this explicitly. Options include:
   - A Zapier workflow that logs every Notion page update to a separate "Order Change Log" database (timestamp, field changed, old value, new value)
   - Relying on the Notion → BigQuery ETL to capture snapshots (but this only gives periodic snapshots, not real-time change tracking)
   - Accepting the loss — if the team doesn't actively use version history today, this may be acceptable
2. **Migration scripts** must deduplicate to latest version per `id` (using `synced_at DESC`) — we migrate the current state, not the full history
3. **Historical versions stay in BigQuery** — the `Knoxx_Freshline` dataset should be retained as a read-only archive even after FL is decommissioned, preserving the version history for any future queries

---

## 3. Downstream Dependencies

### BigQuery Datasets That Reference FL Data

| Dataset | Tables | Impact |
|---|---|---|
| `Dashboards` | `Reporting_FL_Stats`, `Reporting_Sales_Dashboard_FL`, `Reporting_Pricing_Dashboard`, `Reporting_Sales_Forecast_vs_Actuals`, and others | These views/tables join on FL data — need to be re-pointed to Notion-sourced tables post-migration |
| `Zapier` | `Customers`, `actuals`, `quarterly_forecast_vs_actuals_by_product` | Zapier-originated data including customer list and forecast comparisons |
| `Chat_bot` | `Pricing_Charges` | Used by Louna pricing agent — needs to survive migration |
| `Carton_Cloud` | Stock reports (4 tables) | Independent of FL, but CC sales orders currently link back via `carton-cloud-sales-order-id` custom data |
| `Knoxx_QB_Tables` | 35 tables (invoices, bills, payments, customers, items) | QB data is ETL'd independently via Skyvia — no direct FL dependency, but cross-dataset joins exist |

### Automation Dependencies

| Automation | Current FL Touchpoint | Post-Migration Change |
|---|---|---|
| FL→CC hourly cron | Reads confirmed FL orders → creates CC sales orders | Reads from Notion orders DB → creates CC sales orders |
| POD workflow | Writes POD status back to FL | Writes POD status to Notion |
| Run sheet generation | Pulls order addresses from FL | Pulls from Notion |
| Lot/BBD sync | Writes CC pick data back to FL line items | Writes to Notion line items |
| Order completion | Checks POD criteria in FL | Checks POD criteria in Notion |
| FL browser automation (Apify actors) | 4 actors interact with FL UI | **Retired entirely** — no longer needed |
| QB invoice sync | FL native integration (via custom data) | Needs replacement — Zapier/Make workflow or direct Notion→QB integration |

### What Gets Retired

- All 4 Apify actors (`freshline-order-attachment-apify`, `freshline-order-updater-apify`, `freshline-line-item-updater`, `freshline-order-attachment-apify`)
- The `fl_orders_to_process` queue table (replaced by Notion database query)
- FL-specific Zapier triggers/searches

---

## 4. Proposed Notion Database Architecture

### Entity Relationship Diagram

See [freshline-to-notion-erd.mermaid](freshline-to-notion-erd.mermaid) for the full diagram. Summary below.

### Core Databases

| Database | Migrated Records | Ongoing Growth | Source |
|---|---|---|---|
| **Customers** | 98 | Slow (new accounts) | `freshline_customers` + customer-level `custom_data` |
| **Contacts** | 185 | Slow | `freshline_contacts` + contact-level `custom_data` |
| **Products** | 105 | Slow (new SKUs) | `freshline_products` |
| **Product Variants** | 107 | Slow | `freshline_product_variants` + variant-level `custom_data` |
| **Locations** | TBD (deduplicated from orders) | Slow | FL has a native Locations table (not synced to BQ — location fields are flattened into orders at ETL time). Migration should extract from either FL directly or deduplicate from order-level address fields in BQ. |
| **Customer Pricing** | TBD | As prices change | **Extract from FL directly** — not in BQ. Junction table: Customer × Product Variant → unit price. Powers automated price lookup on line item creation. |
| **Orders** | 987 | ~115/month | `freshline_orders` + order-level `custom_data` |
| **Order Line Items** | 1,919 | ~230/month | `freshline_order_line_items` (note: rollups from Product Variant replace denormalised fields; `unit_price` populated by automation from Customer Pricing lookup) |
| **Order Fee Items** | 56 | ~6/month | `freshline_order_fee_items` |

### Supporting Databases

| Database | Purpose |
|---|---|
| **Order Change Log** (optional) | Structured audit trail — replaces BQ version history. Populated by Zapier on each Notion page update. Only needed if the team actively queries order state changes. |
| **Archive — Orders** | Completed orders older than 6 months, moved periodically to keep the active Orders DB lean. |

### Design Decisions

1. **Flatten custom_data into order/customer properties** — no need for a separate key-value store in Notion. QB IDs, CC IDs, pallet status, etc. become first-class properties.
2. **Locations as a first-class database** — FL has a native Locations table, but the BQ ETL flattens location fields into each order row. Notion should restore Locations as a proper standalone database with relations to Customers and Orders.
3. **Money as numbers, not integers** — FL stores amounts in cents (integer). Convert to decimal on migration.
4. **Migrate current state only** — migration scripts deduplicate to the latest version per `id` (by `synced_at DESC`). The full version history remains in BigQuery's `Knoxx_Freshline` dataset as a read-only archive.
5. **Decide on change log** — if the team needs an ongoing audit trail of order state changes, build a Zapier workflow that writes to the Order Change Log DB on every Notion page update. If not, accept the loss and rely on Notion's built-in (non-API) page history for ad-hoc lookups.
6. **Customer Pricing as a junction table** — Customer × Product Variant → unit price. Replaces FL's internal price list (which is not synced to BQ). When a line item is created with a Product Variant relation, a Zapier automation looks up the price and writes it to `unit_price`. The field remains editable for per-order overrides.
7. **Line items use rollups for reference data** — product name, SKU, case size, unit are rolled up from the Product Variant relation rather than denormalised. Only writable/variable fields (quantity, unit_price, notes) live directly on the line item.

---

## 5. Integration Rewiring

### QuickBooks (Critical Path)

FL currently has a native QB integration that:
- Creates invoices from completed orders
- Syncs customer IDs bidirectionally
- Links products to QB items

**Options:**
1. **Zapier: Notion → QB** — trigger on order status change to "completed" → create QB invoice. Most aligned with existing stack.
2. **Make.com** — alternative if Zapier's QB actions are insufficient.
3. **Direct API** — overkill for this volume.

**Recommendation:** Zapier workflow. We already have QB connected. Build a multi-step Zap that triggers on Notion order status change → maps line items → creates QB invoice → writes QB invoice ID back to Notion.

### CartonCloud

Current FL→CC sync becomes Notion→CC sync:
- **Trigger:** Notion order status changes to "confirmed"
- **Action:** Create/update CC sales order via the existing `zapier-cartoncloud` Platform CLI integration
- **Reverse sync:** CC dispatch/POD data writes back to Notion order properties

The custom CartonCloud Zapier app doesn't need changes — only the trigger source changes from BigQuery query to Notion database query.

### ETL: Notion → BigQuery

Required for all reporting/dashboard dependencies and Louna.

Note: Freshline currently pipes data to BigQuery via its own **native BQ integration** (not Skyvia). This integration goes away when FL is decommissioned, so we need a replacement ETL path from Notion.

| Option | Pros | Cons |
|---|---|---|
| **Skyvia** (existing) | Already in use for QB ETL; no new vendor | Notion connector quality unknown; may have sync lag |
| **Fivetran** | Best-in-class Notion connector; reliable incremental sync | New vendor, additional cost |
| **Zapier** | Already in stack; trigger on page changes | Not designed for bulk ETL; rate limit concerns |

**Recommendation:** Sai to evaluate Skyvia's Notion connector first (since it's already paid for). If inadequate, move to Fivetran. This is Sai's decision per the meeting.

---

## 6. Migration Execution Plan

### Phase 0: Prep (Week of 31 March – 6 April)

- [ ] Finalise this architecture document (review with Sai on Wed 1 April)
- [ ] Wrap up shipping status update tickets (KF blockers)
- [ ] Set up Notion workspace structure (empty databases with correct schemas)
- [ ] Prototype QB invoice creation Zap (Notion trigger → QB create invoice)

### Phase 1: Data Migration (Week of 7–13 April)

- [ ] **Extract data not in BQ directly from Freshline:**
  - Customer × SKU price list (the master pricing table)
  - Locations table
- [ ] Write migration scripts:
  - Customers + Contacts (from BQ → Notion API, preserving FL IDs as properties)
  - Products + Variants
  - Customer Pricing (from FL extraction → Notion)
  - Locations (from FL extraction → Notion)
  - Historical orders + line items + fee items (batch, likely Python + Notion SDK)
- [ ] Flatten custom_data into order/customer properties during migration
- [ ] Validate: row counts match, spot-check 20 orders end-to-end

### Phase 2: Automation Rewiring (Weeks of 14–27 April)

- [ ] Build Notion→CC order sync Zap (replaces FL→CC cron)
- [ ] Build CC→Notion reverse sync (POD, lot/BBD, dispatch status)
- [ ] Build Notion→QB invoice Zap
- [ ] Build run sheet generation from Notion data
- [ ] Build order completion logic against Notion POD criteria
- [ ] Set up ETL: Notion → BigQuery (Skyvia or Fivetran)
- [ ] Re-point Dashboard views to Notion-sourced BQ tables

### Phase 3: Parallel Run (Weeks of 28 April – 18 May)

- [ ] Run FL and Notion side-by-side for 2–3 weeks
- [ ] All new orders entered in Notion, synced to FL as backup
- [ ] Compare: orders, invoices, CC sync, reporting outputs
- [ ] Fix discrepancies

### Phase 4: Cutover (Target: Late May weekend)

- [ ] Friday PM: final FL data export + sync
- [ ] Disable FL automations
- [ ] Enable Notion-only automations
- [ ] Monday AM: team starts fresh on Notion
- [ ] 1 week hypercare

### Phase 5: Cleanup (June)

- [ ] Decommission Apify actors (4 actors)
- [ ] Remove FL-specific Zapier triggers/Zaps
- [ ] Retain `Knoxx_Freshline` dataset in BQ as read-only archive (preserves full version history); drop `Freshline_Processed` tables (no longer needed)
- [ ] Update Louna agent data sources if needed
- [ ] Cancel Freshline subscription before 1 July

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Notion API rate limits bottleneck CC sync at 600+ orders/month | Medium | High | Batch operations; use Notion bulk create; monitor rate limit headers |
| QB invoice logic more complex than expected (tax, fees, credit memos) | Medium | High | Prototype early in Phase 0; involve Prabhleen for validation |
| Historical data migration has mapping gaps (orphaned contacts, broken relations) | Medium | Medium | Run data quality checks in BQ before migration; handle orphans gracefully |
| Order volume continues to grow, stressing Notion DB performance | Low | Medium | Archive strategy; ETL to BQ for heavy queries |
| Parallel run reveals edge cases not covered | Medium | Medium | Buffer 2–3 weeks before hard cutover; maintain FL as read-only fallback |
| ETL from Notion → BQ is unreliable or laggy | Medium | High | Evaluate ETL tool early (Phase 0); have Zapier webhook fallback |
| FL price list extraction fails or is incomplete | Medium | High | Extract early in Phase 1; cross-validate against most-recent-order prices in BQ; have Knoxx team manually verify a sample |

---

## 8. Open Questions

1. **QB invoice creation:** Does FL currently auto-create invoices on order completion, or is this manual? Need to understand the exact trigger and field mapping.
2. **Customer portal:** Deferred per meeting, but the Notion DB schema should accommodate it. Confirm Lovable + magic link auth approach.
3. **Louna data sources:** `Chat_bot.Pricing_Charges` and BQ queries power Louna. Post-migration, do we update the BQ source tables or re-point Louna to Notion directly?
4. **Order entry workflow:** Who enters orders today, and how? FL has a UI for this — Notion will need views/forms that match the team's workflow.
5. **FL data extraction method:** Freshline has no API. How do we extract the customer × SKU price list and Locations table? Options: browser automation (Apify actor), database export if FL provides one, or manual CSV export by the Knoxx team. Need to determine the most reliable approach early.
6. **Price list maintenance:** Who updates customer-specific prices today, and how often? This determines whether the Customer Pricing DB needs an admin workflow or is mostly static.

---

## Appendix: Dataset Dependency Map

```
Freshline (RETIRING)
  └── Knoxx_Freshline (BQ) ──ETL──→ Freshline_Processed (BQ)
       │                              └── fl_orders_to_process → Zapier cron → CC
       │
       ├── custom_data ──links──→ Knoxx_QB_Tables (QB invoice/customer IDs)
       ├── custom_data ──links──→ Carton_Cloud (CC sales order IDs)
       │
       └── Dashboards (BQ views)
            ├── Reporting_FL_Stats
            ├── Reporting_Sales_Dashboard_FL
            ├── Reporting_Pricing_Dashboard
            └── ...

Notion (NEW SOURCE OF TRUTH)
  └── Notion DBs ──ETL──→ BQ staging tables (replace Knoxx_Freshline)
       │                    └── Dashboard views re-pointed here
       │
       ├── Zapier ──trigger──→ CartonCloud (order sync)
       ├── Zapier ──trigger──→ QuickBooks (invoice creation)
       └── Zapier ──reverse──← CartonCloud (POD, lot/BBD)
```
