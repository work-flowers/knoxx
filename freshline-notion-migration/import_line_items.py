"""
Import historical Freshline order line items into Notion Order Line Items database.

Reads order-line-items-data.csv, resolves Order and Product relations via lookup maps,
and creates one Notion page per line item.

Usage:
    1. Ensure .env has NOTION_API_KEY
    2. Ensure lookup maps exist: existing-order-ids.json, lookup-products.json
    3. python import_line_items.py [--dry-run] [--limit N] [--offset N]
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
CSV_PATH = SCRIPT_DIR / "order-line-items-data.csv"
ORDERS_LOOKUP_PATH = SCRIPT_DIR / "existing-order-ids.json"
PRODUCTS_LOOKUP_PATH = SCRIPT_DIR / "lookup-products.json"
EXISTING_LI_PATH = SCRIPT_DIR / "existing-line-item-ids.json"
LOG_PATH = SCRIPT_DIR / "import-line-items-log.json"

# Notion data source ID for Order Line Items
LINE_ITEMS_DATA_SOURCE_ID = "33c8094c-3d8a-8074-a5b3-000bc7dad468"


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


def safe_float(val: str) -> float | None:
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: str) -> int | None:
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def build_rich_text(text: str) -> list:
    if not text or text.strip() == "":
        return []
    return [{"type": "text", "text": {"content": text[:2000]}}]


def build_line_item_properties(row: dict, order_page_id: str | None, product_page_id: str | None) -> dict:
    props = {}

    # Title: variant_sku + product_name combo for readability
    sku = row.get("variant_sku", "")
    pname = row.get("product_name", "")
    title = f"{sku} — {pname}" if sku and pname else sku or pname or "Untitled Line Item"
    props["Name"] = {
        "title": [{"type": "text", "text": {"content": title[:2000]}}]
    }

    # Freshline IDs for traceability
    props["Freshline line item ID"] = {"rich_text": build_rich_text(row.get("freshline_line_item_id", ""))}
    props["Freshline order ID"] = {"rich_text": build_rich_text(row.get("order_id", ""))}
    props["Freshline variant ID"] = {"rich_text": build_rich_text(row.get("variant_id", ""))}

    # Text fields
    props["Product name"] = {"rich_text": build_rich_text(row.get("product_name", ""))}
    props["Variant name"] = {"rich_text": build_rich_text(row.get("variant_name", ""))}
    props["Variant SKU"] = {"rich_text": build_rich_text(row.get("variant_sku", ""))}
    props["Variant unit"] = {"rich_text": build_rich_text(row.get("variant_unit", ""))}

    # Number fields
    for csv_col, notion_prop in [
        ("variant_case_size", "Variant case size"),
        ("unit_quantity", "Unit quantity"),
        ("unit_price", "Unit price"),
        ("subtotal", "Subtotal"),
        ("total", "Total"),
        ("tax", "Tax"),
        ("tax_rate", "Tax rate"),
        ("stock_cost", "Stock cost"),
    ]:
        val = safe_float(row.get(csv_col, ""))
        if val is not None:
            props[notion_prop] = {"number": val}

    # Price rule fields
    props["Price rule type"] = {"rich_text": build_rich_text(row.get("price_rule_type", ""))}
    props["Price rule value"] = {"rich_text": build_rich_text(row.get("price_rule_value", ""))}

    # Notes
    for csv_col, notion_prop in [
        ("customer_notes", "Customer notes"),
        ("internal_notes", "Internal notes"),
        ("invoice_notes", "Invoice notes"),
    ]:
        val = row.get(csv_col, "")
        if val and val.strip():
            props[notion_prop] = {"rich_text": build_rich_text(val)}

    # Relations
    if order_page_id:
        props["Order"] = {"relation": [{"id": order_page_id}]}

    if product_page_id:
        props["Product"] = {"relation": [{"id": product_page_id}]}

    return props


def main():
    parser = argparse.ArgumentParser(description="Import Freshline order line items into Notion")
    parser.add_argument("--dry-run", action="store_true", help="Print without creating pages")
    parser.add_argument("--limit", type=int, default=None, help="Max items to import")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N items")
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
    orders_map = load_lookup(ORDERS_LOOKUP_PATH)       # freshline_order_id -> page_id
    products_map = load_lookup(PRODUCTS_LOOKUP_PATH)    # freshline_variant_id -> page_id
    print(f"  Orders:   {len(orders_map)} entries")
    print(f"  Products: {len(products_map)} entries")

    # Load existing line item IDs to skip already-imported items
    existing_ids = {}
    if EXISTING_LI_PATH.exists():
        existing_ids = load_lookup(EXISTING_LI_PATH)
        print(f"  Existing line items to skip: {len(existing_ids)} entries")

    # Load CSV
    print(f"Loading {CSV_PATH}...")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    total = len(reader)
    print(f"  {total} line items in CSV")

    # Apply offset and limit
    rows = reader[args.offset:]
    if args.limit:
        rows = rows[:args.limit]
    print(f"  Processing {len(rows)} line items (offset={args.offset}, limit={args.limit})")

    # Import loop
    log = {"created": [], "order_orphans": [], "product_orphans": [], "errors": []}
    created_count = 0
    skipped_count = 0

    for i, row in enumerate(rows):
        fl_li_id = row.get("freshline_line_item_id", f"row-{i}")
        fl_order_id = row.get("order_id", "")
        fl_variant_id = row.get("variant_id", "")
        sku = row.get("variant_sku", "")

        # Skip already-imported items
        if fl_li_id and fl_li_id in existing_ids:
            skipped_count += 1
            continue

        # Resolve order
        order_page_id = orders_map.get(fl_order_id)
        if not order_page_id and fl_order_id:
            log["order_orphans"].append({
                "line_item": fl_li_id,
                "freshline_order_id": fl_order_id,
                "sku": sku,
            })

        # Resolve product by variant_id
        product_page_id = products_map.get(fl_variant_id)
        if not product_page_id and fl_variant_id:
            log["product_orphans"].append({
                "line_item": fl_li_id,
                "freshline_variant_id": fl_variant_id,
                "sku": sku,
            })

        # Build properties
        props = build_line_item_properties(row, order_page_id, product_page_id)

        if args.dry_run:
            order_status = "✓" if order_page_id else "✗"
            product_status = "✓" if product_page_id else "✗"
            print(f"  [DRY RUN] {sku} | Order {order_status} | Product {product_status}")
            created_count += 1
            continue

        # Create page
        try:
            result = notion.pages.create(
                parent={"type": "data_source_id", "data_source_id": LINE_ITEMS_DATA_SOURCE_ID},
                properties=props,
            )
            page_id = result["id"]
            log["created"].append({
                "freshline_line_item_id": fl_li_id,
                "freshline_order_id": fl_order_id,
                "sku": sku,
                "notion_page_id": page_id,
            })
            existing_ids[fl_li_id] = page_id
            created_count += 1

            # Progress + incremental save every 50
            if created_count % 50 == 0 or created_count == len(rows) - skipped_count:
                print(f"  [{created_count}/{len(rows) - skipped_count}] Created {sku} -> {page_id}")
                with open(EXISTING_LI_PATH, "w") as sf:
                    json.dump(existing_ids, sf, indent=2)
                with open(LOG_PATH, "w") as lf:
                    json.dump(log, lf, indent=2)

        except APIResponseError as e:
            if e.status == 429:
                retry_after = float(e.headers.get("Retry-After", 1)) if hasattr(e, 'headers') else 1
                print(f"  Rate limited at {sku}, waiting {retry_after}s...")
                time.sleep(retry_after)
                try:
                    result = notion.pages.create(
                        parent={"type": "data_source_id", "data_source_id": LINE_ITEMS_DATA_SOURCE_ID},
                        properties=props,
                    )
                    page_id = result["id"]
                    log["created"].append({
                        "freshline_line_item_id": fl_li_id,
                        "freshline_order_id": fl_order_id,
                        "sku": sku,
                        "notion_page_id": page_id,
                    })
                    existing_ids[fl_li_id] = page_id
                    created_count += 1
                except Exception as e2:
                    log["errors"].append({"line_item": fl_li_id, "sku": sku, "error": str(e2)})
                    print(f"  ERROR (retry) {sku}: {e2}")
            else:
                log["errors"].append({"line_item": fl_li_id, "sku": sku, "error": str(e)})
                print(f"  ERROR {sku}: {e}")

        except Exception as e:
            log["errors"].append({"line_item": fl_li_id, "sku": sku, "error": str(e)})
            print(f"  ERROR {sku}: {e}")

        # Throttle to stay under rate limits (~3 req/s)
        time.sleep(0.35)

    # Write log
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    # Update existing-line-item-ids.json with newly created items
    if not args.dry_run and log["created"]:
        for entry in log["created"]:
            existing_ids[entry["freshline_line_item_id"]] = entry["notion_page_id"]
        with open(EXISTING_LI_PATH, "w") as f:
            json.dump(existing_ids, f, indent=2)
        print(f"  Updated {EXISTING_LI_PATH} ({len(existing_ids)} total entries)")

    # Summary
    print(f"\n{'='*60}")
    print(f"Import complete {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Skipped (existing): {skipped_count}")
    print(f"  Created:            {created_count}")
    print(f"  Order orphans:      {len(log['order_orphans'])}")
    print(f"  Product orphans:    {len(log['product_orphans'])}")
    print(f"  Errors:             {len(log['errors'])}")
    print(f"  Log saved to:       {LOG_PATH}")


if __name__ == "__main__":
    main()
