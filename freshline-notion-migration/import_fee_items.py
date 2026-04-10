"""
Import Freshline order fee items into Notion Order Fee Items database.

Reads fee item data from BQ JSON extract, resolves Order relations via
existing-order-ids.json lookup, and creates one Notion page per fee item.

Usage:
    1. Add your Notion API key to .env (NOTION_API_KEY=ntn_...)
    2. python import_fee_items.py [--dry-run] [--limit N]

Options:
    --dry-run   Print what would be created without making API calls
    --limit N   Only import N fee items (useful for testing)
"""

import csv
import json
import os
import sys
import time
import argparse
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
FEE_ITEMS_CSV = SCRIPT_DIR / "order-fee-items-data.csv"
EXISTING_ORDER_IDS = SCRIPT_DIR / "existing-order-ids.json"
EXISTING_FEE_ITEM_IDS = SCRIPT_DIR / "existing-fee-item-ids.json"
LOG_PATH = SCRIPT_DIR / "import-fee-items-log.json"

# Notion data source ID for Order Fee Items
FEE_ITEMS_DATA_SOURCE_ID = "08f0af87-e3e4-46b9-b2f5-589b61c4192e"

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def load_env():
    """Load .env file into environment."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


def load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if missing."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def safe_float(val) -> float | None:
    """Safely convert a value to float, returning None for empty/invalid."""
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def build_rich_text(text: str) -> list:
    """Build a Notion rich_text array from a string."""
    if not text or str(text).strip() == "":
        return []
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def build_fee_item_properties(row: dict, order_page_id: str | None) -> dict:
    """Build the Notion properties dict for a fee item page."""
    props = {}

    description = row.get("description", "") or ""

    # Title: use description as the page name
    props["Name"] = {
        "title": [{"type": "text", "text": {"content": description or "Untitled Fee"}}]
    }

    # Type (select)
    fee_type = (row.get("type", "") or "").strip().lower()
    if fee_type in ("service", "fulfillment", "discount"):
        props["Type"] = {"select": {"name": fee_type}}

    # Description (rich_text — separate from title for filtering/search)
    if description:
        props["Description"] = {"rich_text": build_rich_text(description)}

    # Amount (number, AUD) — already converted from cents in BQ query
    amount = safe_float(row.get("amount"))
    if amount is not None:
        props["Amount"] = {"number": amount}

    # Percentage (number, percent format — Notion stores as decimal: 1.5% = 0.015)
    pct = safe_float(row.get("percentage"))
    if pct is not None:
        props["Percentage"] = {"number": pct / 100.0}

    # Freshline fee item ID (rich_text)
    fl_id = row.get("freshline_fee_item_id", "")
    if fl_id:
        props["Freshline fee item ID"] = {"rich_text": build_rich_text(fl_id)}

    # Freshline order ID (rich_text)
    fl_order_id = row.get("freshline_order_id", "")
    if fl_order_id:
        props["Freshline order ID"] = {"rich_text": build_rich_text(fl_order_id)}

    # Order relation
    if order_page_id:
        props["Order"] = {"relation": [{"id": order_page_id}]}

    return props


def create_notion_page(api_key: str, properties: dict) -> dict:
    """Create a Notion page via REST API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": FEE_ITEMS_DATA_SOURCE_ID},
        "properties": properties,
    }
    resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code == 429:
        retry_after = float(resp.headers.get("Retry-After", 1))
        raise RateLimitError(retry_after)
    resp.raise_for_status()
    return resp.json()


class RateLimitError(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


def main():
    parser = argparse.ArgumentParser(description="Import Freshline fee items into Notion")
    parser.add_argument("--dry-run", action="store_true", help="Print without creating pages")
    parser.add_argument("--limit", type=int, default=None, help="Max fee items to import")
    args = parser.parse_args()

    # Load env
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY not set. Add it to .env")
        sys.exit(1)

    # Load lookup maps
    print("Loading lookup maps...")
    order_ids_map = load_json(EXISTING_ORDER_IDS)
    existing_fee_ids = load_json(EXISTING_FEE_ITEM_IDS)
    print(f"  Order lookup:          {len(order_ids_map)} entries")
    print(f"  Existing fee items:    {len(existing_fee_ids)} entries")

    # Load CSV
    print(f"Loading {FEE_ITEMS_CSV}...")
    with open(FEE_ITEMS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} fee items in CSV")

    if args.limit:
        rows = rows[:args.limit]
        print(f"  Limited to {len(rows)} fee items")

    # Import loop
    log = {"created": [], "order_orphans": [], "skipped": [], "errors": []}
    created_count = 0
    skipped_count = 0

    for i, row in enumerate(rows):
        fl_fee_id = row.get("freshline_fee_item_id", "")
        fl_order_id = row.get("freshline_order_id", "")
        description = row.get("description", "")

        # Skip already-imported fee items
        if fl_fee_id and fl_fee_id in existing_fee_ids:
            skipped_count += 1
            continue

        # Resolve order relation
        order_page_id = order_ids_map.get(fl_order_id)
        if not order_page_id:
            log["order_orphans"].append({
                "freshline_fee_item_id": fl_fee_id,
                "freshline_order_id": fl_order_id,
                "description": description,
            })
            # Still create the fee item, just without the relation
            print(f"  WARNING: No order found for {fl_order_id} (fee: {fl_fee_id})")

        # Build properties
        props = build_fee_item_properties(row, order_page_id)

        if args.dry_run:
            order_status = "✓" if order_page_id else "✗"
            print(f"  [DRY RUN] {fl_fee_id} | {row.get('type', '')} | {description} | Order {order_status}")
            created_count += 1
            continue

        # Create page
        try:
            result = create_notion_page(api_key, props)
            page_id = result["id"]
            log["created"].append({
                "freshline_fee_item_id": fl_fee_id,
                "freshline_order_id": fl_order_id,
                "notion_page_id": page_id,
                "description": description,
            })
            existing_fee_ids[fl_fee_id] = page_id
            created_count += 1

            if created_count % 10 == 0:
                print(f"  [{created_count}/{len(rows) - skipped_count}] Created: {description}")

        except RateLimitError as e:
            print(f"  Rate limited, waiting {e.retry_after}s...")
            time.sleep(e.retry_after)
            try:
                result = create_notion_page(api_key, props)
                page_id = result["id"]
                log["created"].append({
                    "freshline_fee_item_id": fl_fee_id,
                    "freshline_order_id": fl_order_id,
                    "notion_page_id": page_id,
                    "description": description,
                })
                existing_fee_ids[fl_fee_id] = page_id
                created_count += 1
            except Exception as e2:
                log["errors"].append({"fee_id": fl_fee_id, "error": str(e2)})
                print(f"  ERROR (retry) {fl_fee_id}: {e2}")

        except Exception as e:
            log["errors"].append({"fee_id": fl_fee_id, "error": str(e)})
            print(f"  ERROR {fl_fee_id}: {e}")

        # Throttle to stay under rate limits (~3 req/s)
        time.sleep(0.35)

    # Write log
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    # Update existing-fee-item-ids.json
    if not args.dry_run and log["created"]:
        with open(EXISTING_FEE_ITEM_IDS, "w") as f:
            json.dump(existing_fee_ids, f, indent=2)
        print(f"  Updated {EXISTING_FEE_ITEM_IDS} ({len(existing_fee_ids)} total entries)")

    # Summary
    print(f"\n{'='*60}")
    print(f"Import complete {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Skipped (existing): {skipped_count}")
    print(f"  Created:            {created_count}")
    print(f"  Order orphans:      {len(log['order_orphans'])}")
    print(f"  Errors:             {len(log['errors'])}")
    print(f"  Log saved to:       {LOG_PATH}")


if __name__ == "__main__":
    main()
