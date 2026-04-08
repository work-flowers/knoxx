"""
Import historical Freshline orders into Notion Orders database.

Reads orders-data.csv, resolves Customer and Contact relations via lookup maps,
and creates one Notion page per order in the Orders data source.

Usage:
    1. Add your Notion API key to .env (NOTION_API_KEY=ntn_...)
    2. python import_orders.py [--dry-run] [--limit N] [--offset N]

Options:
    --dry-run   Print what would be created without making API calls
    --limit N   Only import N orders (useful for testing)
    --offset N  Skip the first N orders (useful for resuming)
"""

import csv
import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from notion_client import Client
from notion_client.errors import APIResponseError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
CSV_PATH = SCRIPT_DIR / "orders-data.csv"
CUSTOMERS_LOOKUP_PATH = SCRIPT_DIR / "lookup-customers.json"
CONTACTS_LOOKUP_PATH = SCRIPT_DIR / "lookup-contacts.json"
LOG_PATH = SCRIPT_DIR / "import-orders-log.json"
EXISTING_IDS_PATH = SCRIPT_DIR / "existing-order-ids.json"

# Notion data source ID for Orders
ORDERS_DATA_SOURCE_ID = "b04f62ec-bb3d-448b-852e-8ac82433bec1"

# State mapping: Freshline state names -> Notion select option names
STATE_MAP = {
    "open": "open",
    "confirmed": "confirmed",
    "complete": "complete",
    "cancelled": "cancelled",
    "draft": "draft",
}

# Fulfilment type mapping
FULFILMENT_TYPE_MAP = {
    "delivery": "delivery",
    "pickup": "pickup",
}


def load_env():
    """Load .env file into environment."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


def load_lookup(path: Path) -> dict:
    """Load a JSON lookup map."""
    with open(path) as f:
        return json.load(f)


def ts_to_unix_seconds(ts_str: str) -> int | None:
    """Convert a timestamp string (e.g. '2025-08-01 03:22:10 UTC') to unix seconds."""
    if not ts_str or ts_str.strip() == "":
        return None
    try:
        # Handle various timestamp formats from BQ
        ts_str = ts_str.strip().replace(" UTC", "+00:00").replace(" ", "T")
        if "+" not in ts_str and "Z" not in ts_str:
            ts_str += "+00:00"
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def safe_float(val: str) -> float | None:
    """Safely convert a string to float, returning None for empty/invalid."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: str) -> int | None:
    """Safely convert a string to int, returning None for empty/invalid."""
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def build_rich_text(text: str) -> list:
    """Build a Notion rich_text array from a string."""
    if not text or text.strip() == "":
        return []
    # Notion rich_text has a 2000 char limit per block
    return [{"type": "text", "text": {"content": text[:2000]}}]


def build_order_properties(row: dict, customer_page_id: str | None, contact_page_id: str | None) -> dict:
    """Build the Notion properties dict for an order page."""
    props = {}

    # Title: order number
    order_number = row.get("order_number", "")
    props["Order Title"] = {
        "title": [{"type": "text", "text": {"content": order_number or "Untitled Order"}}]
    }

    # Freshline order ID (text)
    props["Freshline order ID"] = {"rich_text": build_rich_text(row.get("freshline_order_id", ""))}

    # Freshline customer ID (text, for traceability)
    props["Freshline customer ID"] = {"rich_text": build_rich_text(row.get("customer_id", ""))}

    # Freshline contact ID (text)
    props["Freshline contact ID"] = {"rich_text": build_rich_text(row.get("contact_id", ""))}

    # State (select)
    state_raw = (row.get("state", "") or "").strip().lower()
    state_mapped = STATE_MAP.get(state_raw)
    if state_mapped:
        props["State"] = {"select": {"name": state_mapped}}

    # Fulfilment date (date)
    fdate = row.get("fulfillment_date", "")
    if fdate and fdate.strip():
        props["Fulfilment date"] = {"date": {"start": fdate.strip()}}

    # Fulfilment type (select)
    ftype_raw = (row.get("fulfillment_type", "") or "").strip().lower()
    ftype_mapped = FULFILMENT_TYPE_MAP.get(ftype_raw)
    if ftype_mapped:
        props["Fulfilment type"] = {"select": {"name": ftype_mapped}}

    # Net terms (number)
    net_terms = safe_int(row.get("net_terms", ""))
    if net_terms is not None:
        props["Net terms (days)"] = {"number": net_terms}

    # Historical (checkbox)
    historical = (row.get("historical", "") or "").strip().lower()
    props["Historical"] = {"checkbox": historical == "true"}

    # Money fields (number, stored in dollars)
    for csv_col, notion_prop in [
        ("subtotal", "Subtotal"),
        ("total", "Total"),
        ("tax", "Tax"),
        ("fulfillment_fee", "Fulfilment fee"),
    ]:
        val = safe_float(row.get(csv_col, ""))
        if val is not None:
            props[notion_prop] = {"number": val}

    # Line items count
    lic = safe_int(row.get("line_items_count", ""))
    if lic is not None:
        props["Line items count"] = {"number": lic}

    # Timestamp fields (stored as unix seconds in number properties)
    for csv_col, notion_prop in [
        ("opened_at", "Opened at (unix seconds)"),
        ("confirmed_at", "Confirmed at (unix seconds)"),
        ("completed_at", "Completed at (unix seconds)"),
        ("cancelled_at", "Cancelled at (unix seconds)"),
    ]:
        unix_ts = ts_to_unix_seconds(row.get(csv_col, ""))
        if unix_ts is not None:
            props[notion_prop] = {"number": unix_ts}

    # Text fields
    for csv_col, notion_prop in [
        ("customer_notes", "Customer notes"),
        ("internal_notes", "Internal notes"),
        ("invoice_notes", "Invoice notes"),
        ("cc_sales_order_id", "CC sales order ID"),
        ("qb_invoice_id", "QB invoice ID"),
    ]:
        val = row.get(csv_col, "")
        if val and val.strip():
            props[notion_prop] = {"rich_text": build_rich_text(val)}

    # Backorder rescheduled (checkbox)
    backorder = (row.get("backorder_rescheduled", "") or "").strip().lower()
    props["Backorder rescheduled"] = {"checkbox": backorder == "true"}

    # Location fields (text)
    for csv_col, notion_prop in [
        ("location_id", "Freshline location ID"),
        ("location_name", "Location name"),
        ("location_address_line1", "Location address line 1"),
        ("location_address_line2", "Location address line 2"),
        ("location_address_city", "Location city"),
        ("location_address_region", "Location region"),
        ("location_address_region_code", "Location region code"),
        ("location_address_postal_code", "Location postal code"),
    ]:
        val = row.get(csv_col, "")
        if val and val.strip():
            props[notion_prop] = {"rich_text": build_rich_text(val)}

    # Relations
    if customer_page_id:
        props["Customers"] = {"relation": [{"id": customer_page_id}]}

    if contact_page_id:
        props["Contacts"] = {"relation": [{"id": contact_page_id}]}

    return props


def main():
    parser = argparse.ArgumentParser(description="Import Freshline orders into Notion")
    parser.add_argument("--dry-run", action="store_true", help="Print without creating pages")
    parser.add_argument("--limit", type=int, default=None, help="Max orders to import")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N orders")
    args = parser.parse_args()

    # Load env and init client
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY not set. Add it to .env")
        sys.exit(1)

    notion = Client(auth=api_key)

    # Load lookup maps
    print("Loading lookup maps...")
    customers_map = load_lookup(CUSTOMERS_LOOKUP_PATH)  # freshline_id -> page_id
    contacts_map = load_lookup(CONTACTS_LOOKUP_PATH)     # email -> {page_id, name}
    print(f"  Customers: {len(customers_map)} entries")
    print(f"  Contacts:  {len(contacts_map)} entries")

    # Load existing order IDs to skip already-imported orders
    existing_ids = {}
    if EXISTING_IDS_PATH.exists():
        existing_ids = load_lookup(EXISTING_IDS_PATH)
        print(f"  Existing orders to skip: {len(existing_ids)} entries")

    # Load CSV
    print(f"Loading {CSV_PATH}...")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    total = len(reader)
    print(f"  {total} orders in CSV")

    # Apply offset and limit
    rows = reader[args.offset:]
    if args.limit:
        rows = rows[:args.limit]
    print(f"  Processing {len(rows)} orders (offset={args.offset}, limit={args.limit})")

    # Import loop
    log = {"created": [], "customer_orphans": [], "contact_orphans": [], "errors": []}
    created_count = 0

    skipped_count = 0
    for i, row in enumerate(rows):
        order_num = row.get("order_number", f"row-{i}")
        fl_order_id = row.get("freshline_order_id", "")
        fl_customer_id = row.get("customer_id", "")
        contact_email = (row.get("contact_email", "") or "").strip().lower()

        # Skip already-imported orders
        if fl_order_id and fl_order_id in existing_ids:
            skipped_count += 1
            continue

        # Resolve customer
        customer_page_id = customers_map.get(fl_customer_id)
        if not customer_page_id and fl_customer_id:
            log["customer_orphans"].append({
                "order": order_num,
                "freshline_customer_id": fl_customer_id,
            })

        # Resolve contact by email
        contact_page_id = None
        if contact_email:
            contact_entry = contacts_map.get(contact_email)
            if contact_entry:
                contact_page_id = contact_entry["page_id"]
            else:
                log["contact_orphans"].append({
                    "order": order_num,
                    "contact_email": contact_email,
                })

        # Build properties
        props = build_order_properties(row, customer_page_id, contact_page_id)

        if args.dry_run:
            cust_status = "✓" if customer_page_id else "✗"
            contact_status = "✓" if contact_page_id else "✗"
            print(f"  [DRY RUN] {order_num} | Customer {cust_status} | Contact {contact_status}")
            created_count += 1
            continue

        # Create page
        try:
            result = notion.pages.create(
                parent={"type": "data_source_id", "data_source_id": ORDERS_DATA_SOURCE_ID},
                properties=props,
            )
            page_id = result["id"]
            log["created"].append({
                "order_number": order_num,
                "freshline_order_id": fl_order_id,
                "notion_page_id": page_id,
            })
            created_count += 1

            # Progress
            if created_count % 25 == 0 or created_count == len(rows):
                print(f"  [{created_count}/{len(rows)}] Created {order_num} -> {page_id}")

        except APIResponseError as e:
            if e.status == 429:
                # Rate limited — wait and retry
                retry_after = float(e.headers.get("Retry-After", 1)) if hasattr(e, 'headers') else 1
                print(f"  Rate limited at {order_num}, waiting {retry_after}s...")
                time.sleep(retry_after)
                try:
                    result = notion.pages.create(
                        parent={"type": "data_source_id", "data_source_id": ORDERS_DATA_SOURCE_ID},
                        properties=props,
                    )
                    page_id = result["id"]
                    log["created"].append({
                        "order_number": order_num,
                        "freshline_order_id": fl_order_id,
                        "notion_page_id": page_id,
                    })
                    created_count += 1
                except Exception as e2:
                    log["errors"].append({"order": order_num, "error": str(e2)})
                    print(f"  ERROR (retry) {order_num}: {e2}")
            else:
                log["errors"].append({"order": order_num, "error": str(e)})
                print(f"  ERROR {order_num}: {e}")

        except Exception as e:
            log["errors"].append({"order": order_num, "error": str(e)})
            print(f"  ERROR {order_num}: {e}")

        # Throttle to stay under rate limits (~3 req/s)
        time.sleep(0.35)

    # Write log
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    # Update existing-order-ids.json with newly created orders
    if not args.dry_run and log["created"]:
        for entry in log["created"]:
            existing_ids[entry["freshline_order_id"]] = entry["notion_page_id"]
        with open(EXISTING_IDS_PATH, "w") as f:
            json.dump(existing_ids, f, indent=2)
        print(f"  Updated {EXISTING_IDS_PATH} ({len(existing_ids)} total entries)")

    # Summary
    print(f"\n{'='*60}")
    print(f"Import complete {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Skipped (existing): {skipped_count}")
    print(f"  Created:            {created_count}")
    print(f"  Customer orphans:   {len(log['customer_orphans'])}")
    print(f"  Contact orphans:    {len(log['contact_orphans'])}")
    print(f"  Errors:             {len(log['errors'])}")
    print(f"  Log saved to:       {LOG_PATH}")


if __name__ == "__main__":
    main()
