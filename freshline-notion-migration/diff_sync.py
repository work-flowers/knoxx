"""
Diff engine for the daily Freshline -> Notion sync.

Compares fresh BigQuery extracts against local CSV baselines to identify
new, updated, and ghost records. Outputs structured JSON files that the
scheduled task agent uses to drive Notion MCP create/update/archive calls.

Usage:
    python diff_sync.py \
        --orders-bq    /path/to/orders_bq_result.json \
        --lineitems-bq /path/to/lineitems_bq_result.json \
        --feeitems-bq  /path/to/feeitems_bq_result.json

Inputs (read from script directory):
    orders-data.csv              Previous BQ extract (baseline)
    order-line-items-data.csv    Previous BQ extract (baseline)
    order-fee-items-data.csv     Previous BQ extract (baseline)
    existing-order-ids.json      freshline_order_id -> Notion page_id
    existing-line-item-ids.json  freshline_line_item_id -> Notion page_id
    existing-fee-item-ids.json   freshline_fee_item_id -> Notion page_id
    lookup-customers.json        freshline_customer_id -> Notion page_id
    lookup-contacts.json         contact_email -> {page_id, name}
    lookup-products.json         freshline_variant_id -> Notion page_id

Outputs (written to script directory):
    sync-new-orders.json         New orders to create in Notion
    sync-updated-orders.json     Changed orders to patch in Notion
    sync-new-line-items.json     New line items to create
    sync-updated-line-items.json Changed line items to patch
    sync-ghost-line-items.json   Ghost LIs to archive (removed in FL)
    sync-new-fee-items.json      New fee items to create
    sync-updated-fee-items.json  Changed fee items to patch
    sync-summary.json            Counts and details for reporting
    orders-data.csv              Overwritten with fresh BQ data
    order-line-items-data.csv    Overwritten with fresh BQ data
    order-fee-items-data.csv     Overwritten with fresh BQ data
"""

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
ORDERS_CSV = SCRIPT_DIR / "orders-data.csv"
LINE_ITEMS_CSV = SCRIPT_DIR / "order-line-items-data.csv"
FEE_ITEMS_CSV = SCRIPT_DIR / "order-fee-items-data.csv"
EXISTING_ORDER_IDS = SCRIPT_DIR / "existing-order-ids.json"
EXISTING_LI_IDS = SCRIPT_DIR / "existing-line-item-ids.json"
EXISTING_FI_IDS = SCRIPT_DIR / "existing-fee-item-ids.json"
LOOKUP_CUSTOMERS = SCRIPT_DIR / "lookup-customers.json"
LOOKUP_CONTACTS = SCRIPT_DIR / "lookup-contacts.json"
LOOKUP_PRODUCTS = SCRIPT_DIR / "lookup-products.json"

# Output paths
OUT_NEW_ORDERS = SCRIPT_DIR / "sync-new-orders.json"
OUT_UPDATED_ORDERS = SCRIPT_DIR / "sync-updated-orders.json"
OUT_NEW_LI = SCRIPT_DIR / "sync-new-line-items.json"
OUT_UPDATED_LI = SCRIPT_DIR / "sync-updated-line-items.json"
OUT_GHOSTS = SCRIPT_DIR / "sync-ghost-line-items.json"
OUT_NEW_FI = SCRIPT_DIR / "sync-new-fee-items.json"
OUT_UPDATED_FI = SCRIPT_DIR / "sync-updated-fee-items.json"
OUT_SUMMARY = SCRIPT_DIR / "sync-summary.json"

# ---------------------------------------------------------------------------
# Fields to compare for change detection
# ---------------------------------------------------------------------------
ORDER_COMPARE_FIELDS = [
    "state", "fulfillment_date", "fulfillment_type", "net_terms",
    "historical", "subtotal", "total", "tax", "fulfillment_fee",
    "customer_notes", "internal_notes", "invoice_notes", "line_items_count",
    "opened_at_datetime", "confirmed_at_datetime", "completed_at_datetime",
    "cancelled_at_datetime", "cc_sales_order_id", "qb_invoice_id",
    "backorder_rescheduled", "location_name", "location_address_line1",
    "location_address_city", "contact_name", "contact_email",
]

LI_COMPARE_FIELDS = [
    "product_name", "variant_name", "variant_sku", "variant_case_size",
    "variant_unit", "unit_quantity", "unit_price", "subtotal", "total",
    "tax", "tax_rate", "stock_cost", "price_rule_type", "price_rule_value",
    "customer_notes", "internal_notes", "invoice_notes",
]

FI_COMPARE_FIELDS = [
    "type", "description", "amount", "percentage",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalise(value: str | None) -> str:
    """Normalise a value for comparison: None/null/'' -> '', floats to 2dp."""
    if value is None:
        return ""
    v = str(value).strip()
    if v.lower() in ("none", "null", ""):
        return ""
    # Normalise numeric values to 2dp
    try:
        f = float(v)
        return f"{f:.2f}"
    except (ValueError, TypeError):
        return v


def parse_bq_json(path: Path) -> list[dict]:
    """Parse BigQuery JSON result format into list of flat dicts.

    BQ format: {"schema": {"fields": [{"name": ...}]}, "rows": [{"f": [{"v": ...}]}]}
    Also handles plain list-of-dicts format (if BQ returned that way).
    """
    with open(path) as f:
        data = json.load(f)

    # If it's already a list of dicts, return as-is
    if isinstance(data, list):
        return data

    # BQ nested format
    fields = [field["name"] for field in data["schema"]["fields"]]
    rows = []
    for row in data.get("rows", []):
        values = [cell.get("v") for cell in row["f"]]
        rows.append(dict(zip(fields, values)))
    return rows


def load_csv_keyed(path: Path, key_field: str) -> dict[str, dict]:
    """Load a CSV into a dict keyed by key_field."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        result = {}
        for row in reader:
            k = row.get(key_field, "")
            if k:
                result[k] = row
        return result


def load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if missing."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data):
    """Write JSON to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def save_csv(path: Path, rows: list[dict]):
    """Write list of dicts to CSV."""
    if not rows:
        # Write empty file with no headers
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def diff_records(
    fresh: list[dict],
    old_keyed: dict[str, dict],
    existing_ids: dict[str, str],
    id_field: str,
    compare_fields: list[str],
) -> tuple[list[dict], list[dict], int]:
    """Compare fresh BQ records against baseline.

    Returns: (new_records, updated_records, unchanged_count)
    Each updated record includes 'notion_page_id' and 'changed_fields'.
    """
    new_records = []
    updated_records = []
    unchanged = 0

    for row in fresh:
        record_id = str(row.get(id_field, ""))
        if not record_id:
            continue

        if record_id not in existing_ids:
            # New record
            new_records.append(row)
        else:
            # Existing — check for changes
            old_row = old_keyed.get(record_id, {})
            changed_fields = []
            for field in compare_fields:
                old_val = normalise(old_row.get(field))
                new_val = normalise(row.get(field))
                if old_val != new_val:
                    changed_fields.append(field)

            if changed_fields:
                row["notion_page_id"] = existing_ids[record_id]
                row["changed_fields"] = changed_fields
                updated_records.append(row)
            else:
                unchanged += 1

    return new_records, updated_records, unchanged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Diff BQ extracts against baseline for Freshline->Notion sync"
    )
    parser.add_argument(
        "--orders-bq", required=True,
        help="Path to BQ orders JSON result file"
    )
    parser.add_argument(
        "--lineitems-bq", required=True,
        help="Path to BQ line items JSON result file"
    )
    parser.add_argument(
        "--feeitems-bq", required=True,
        help="Path to BQ fee items JSON result file"
    )
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Load inputs
    # -----------------------------------------------------------------------
    print("Loading BQ results...")
    fresh_orders = parse_bq_json(Path(args.orders_bq))
    fresh_li = parse_bq_json(Path(args.lineitems_bq))
    fresh_fi = parse_bq_json(Path(args.feeitems_bq))
    print(f"  Orders from BQ:     {len(fresh_orders)}")
    print(f"  Line items from BQ: {len(fresh_li)}")
    print(f"  Fee items from BQ:  {len(fresh_fi)}")

    print("Loading baselines...")
    old_orders = load_csv_keyed(ORDERS_CSV, "freshline_order_id")
    old_li = load_csv_keyed(LINE_ITEMS_CSV, "freshline_line_item_id")
    old_fi = load_csv_keyed(FEE_ITEMS_CSV, "freshline_fee_item_id")
    print(f"  Baseline orders:     {len(old_orders)}")
    print(f"  Baseline line items: {len(old_li)}")
    print(f"  Baseline fee items:  {len(old_fi)}")

    existing_order_ids = load_json(EXISTING_ORDER_IDS)
    existing_li_ids = load_json(EXISTING_LI_IDS)
    existing_fi_ids = load_json(EXISTING_FI_IDS)
    print(f"  Existing order IDs:  {len(existing_order_ids)}")
    print(f"  Existing LI IDs:     {len(existing_li_ids)}")
    print(f"  Existing FI IDs:     {len(existing_fi_ids)}")

    # Load lookup maps (included in new record output for relation resolution)
    customers_map = load_json(LOOKUP_CUSTOMERS)
    contacts_map = load_json(LOOKUP_CONTACTS)
    products_map = load_json(LOOKUP_PRODUCTS)

    # -----------------------------------------------------------------------
    # Diff orders
    # -----------------------------------------------------------------------
    print("\nDiffing orders...")
    new_orders, updated_orders, unchanged_orders = diff_records(
        fresh_orders, old_orders, existing_order_ids,
        "freshline_order_id", ORDER_COMPARE_FIELDS,
    )
    print(f"  New:       {len(new_orders)}")
    print(f"  Updated:   {len(updated_orders)}")
    print(f"  Unchanged: {unchanged_orders}")

    # Enrich new orders with relation page IDs
    for order in new_orders:
        cust_id = str(order.get("customer_id", ""))
        order["_customer_page_id"] = customers_map.get(cust_id)

        email = (order.get("contact_email") or "").strip().lower()
        contact_entry = contacts_map.get(email)
        order["_contact_page_id"] = contact_entry["page_id"] if contact_entry else None

    # -----------------------------------------------------------------------
    # Diff line items
    # -----------------------------------------------------------------------
    print("\nDiffing line items...")
    new_li, updated_li, unchanged_li = diff_records(
        fresh_li, old_li, existing_li_ids,
        "freshline_line_item_id", LI_COMPARE_FIELDS,
    )
    print(f"  New:       {len(new_li)}")
    print(f"  Updated:   {len(updated_li)}")
    print(f"  Unchanged: {unchanged_li}")

    # Enrich new line items with relation page IDs
    for li in new_li:
        order_id = str(li.get("order_id", ""))
        li["_order_page_id"] = existing_order_ids.get(order_id)

        variant_id = str(li.get("variant_id", ""))
        li["_product_page_id"] = products_map.get(variant_id)

    # -----------------------------------------------------------------------
    # Ghost detection: LIs in existing map but NOT in fresh BQ extract
    # -----------------------------------------------------------------------
    print("\nDetecting ghost line items...")
    fresh_li_ids = {str(li.get("freshline_line_item_id", "")) for li in fresh_li}
    ghost_lis = []
    for li_id, page_id in existing_li_ids.items():
        if li_id not in fresh_li_ids:
            ghost_lis.append({
                "freshline_line_item_id": li_id,
                "notion_page_id": page_id,
            })
    print(f"  Ghosts to archive: {len(ghost_lis)}")

    # -----------------------------------------------------------------------
    # Diff fee items
    # -----------------------------------------------------------------------
    print("\nDiffing fee items...")
    new_fi, updated_fi, unchanged_fi = diff_records(
        fresh_fi, old_fi, existing_fi_ids,
        "freshline_fee_item_id", FI_COMPARE_FIELDS,
    )
    print(f"  New:       {len(new_fi)}")
    print(f"  Updated:   {len(updated_fi)}")
    print(f"  Unchanged: {unchanged_fi}")

    # Enrich new fee items with order relation page IDs
    for fi in new_fi:
        order_id = str(fi.get("freshline_order_id", ""))
        fi["_order_page_id"] = existing_order_ids.get(order_id)

    # -----------------------------------------------------------------------
    # Write outputs
    # -----------------------------------------------------------------------
    print("\nWriting output files...")
    save_json(OUT_NEW_ORDERS, new_orders)
    save_json(OUT_UPDATED_ORDERS, updated_orders)
    save_json(OUT_NEW_LI, new_li)
    save_json(OUT_UPDATED_LI, updated_li)
    save_json(OUT_GHOSTS, ghost_lis)
    save_json(OUT_NEW_FI, new_fi)
    save_json(OUT_UPDATED_FI, updated_fi)

    # Summary
    summary = {
        "orders": {
            "total_in_bq": len(fresh_orders),
            "new": len(new_orders),
            "updated": len(updated_orders),
            "unchanged": unchanged_orders,
        },
        "line_items": {
            "total_in_bq": len(fresh_li),
            "new": len(new_li),
            "updated": len(updated_li),
            "unchanged": unchanged_li,
            "ghosts": len(ghost_lis),
        },
        "fee_items": {
            "total_in_bq": len(fresh_fi),
            "new": len(new_fi),
            "updated": len(updated_fi),
            "unchanged": unchanged_fi,
        },
        "updated_order_details": [
            {
                "order_number": o.get("order_number", ""),
                "freshline_order_id": o.get("freshline_order_id", ""),
                "changed_fields": o.get("changed_fields", []),
            }
            for o in updated_orders
        ],
        "updated_li_details": [
            {
                "freshline_line_item_id": li.get("freshline_line_item_id", ""),
                "variant_sku": li.get("variant_sku", ""),
                "changed_fields": li.get("changed_fields", []),
            }
            for li in updated_li
        ],
        "updated_fi_details": [
            {
                "freshline_fee_item_id": fi.get("freshline_fee_item_id", ""),
                "description": fi.get("description", ""),
                "changed_fields": fi.get("changed_fields", []),
            }
            for fi in updated_fi
        ],
    }
    save_json(OUT_SUMMARY, summary)

    # -----------------------------------------------------------------------
    # Update baseline CSVs with fresh data
    # -----------------------------------------------------------------------
    print("Updating baseline CSVs...")
    save_csv(ORDERS_CSV, fresh_orders)
    save_csv(LINE_ITEMS_CSV, fresh_li)
    save_csv(FEE_ITEMS_CSV, fresh_fi)

    # -----------------------------------------------------------------------
    # Print summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("Diff complete")
    print(f"  Orders:     {len(new_orders)} new, {len(updated_orders)} updated, {unchanged_orders} unchanged")
    print(f"  Line items: {len(new_li)} new, {len(updated_li)} updated, {unchanged_li} unchanged, {len(ghost_lis)} ghosts")
    print(f"  Fee items:  {len(new_fi)} new, {len(updated_fi)} updated, {unchanged_fi} unchanged")

    if updated_orders:
        print("\n  Updated orders:")
        for o in updated_orders:
            print(f"    #{o.get('order_number', '?')}: {', '.join(o.get('changed_fields', []))}")

    if ghost_lis:
        print(f"\n  Ghost line items to archive: {len(ghost_lis)}")

    print(f"\nOutput files written to {SCRIPT_DIR}/sync-*.json")


if __name__ == "__main__":
    main()
