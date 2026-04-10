"""
Reconcile Freshline order totals between BigQuery (via baseline CSV) and Notion.

Compares the local BQ baseline (orders-data.csv, maintained by diff_sync.py)
against live Notion data to surface discrepancies in order counts, totals,
and per-order values.

Usage:
    python reconcile.py --month 2026-03 [--state confirmed,complete] [--verbose]

Options:
    --month YYYY-MM   Month to reconcile (required)
    --state s1,s2     Comma-separated states to include (default: all non-cancelled)
    --verbose         Print per-order comparison details
    --tolerance N     AUD tolerance for flagging per-order mismatches (default: 0.01)
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from notion_client import Client
from notion_client.errors import APIResponseError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
ORDERS_CSV = SCRIPT_DIR / "orders-data.csv"
EXISTING_ORDER_IDS = SCRIPT_DIR / "existing-order-ids.json"

# Notion Orders data source ID
ORDERS_DATA_SOURCE_ID = "b04f62ec-bb3d-448b-852e-8ac82433bec1"

CANCELLED_STATES = {"cancelled"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_env():
    """Load .env file into environment."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


def safe_float(val) -> float:
    """Convert to float, defaulting to 0.0."""
    if val is None or str(val).strip() in ("", "None", "null"):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def parse_month(month_str: str) -> tuple[str, str]:
    """Parse YYYY-MM into (start_date, end_date) for filtering."""
    parts = month_str.split("-")
    year, month = int(parts[0]), int(parts[1])
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    return start, end


def extract_rich_text(prop: dict) -> str:
    """Extract plain text from a Notion rich_text property."""
    if not prop or prop.get("type") != "rich_text":
        return ""
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


def extract_title(prop: dict) -> str:
    """Extract plain text from a Notion title property."""
    if not prop or prop.get("type") != "title":
        return ""
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))


def extract_number(prop: dict) -> float:
    """Extract number from a Notion number, formula, or rollup property."""
    if not prop:
        return 0.0
    ptype = prop.get("type", "")
    if ptype == "number":
        val = prop.get("number")
    elif ptype == "formula":
        inner = prop.get("formula", {})
        val = inner.get("number")
    elif ptype == "rollup":
        inner = prop.get("rollup", {})
        val = inner.get("number")
    else:
        return 0.0
    return float(val) if val is not None else 0.0


def extract_select(prop: dict) -> str:
    """Extract name from a Notion select property."""
    if not prop or prop.get("type") != "select":
        return ""
    sel = prop.get("select")
    return sel.get("name", "") if sel else ""


def extract_date_start(prop: dict) -> str:
    """Extract start date string from a Notion date property."""
    if not prop or prop.get("type") != "date":
        return ""
    d = prop.get("date")
    return d.get("start", "") if d else ""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_bq_orders(month_start: str, month_end: str, include_states: set | None,
                   date_field: str = "opened_at") -> dict:
    """Load orders from BQ baseline CSV, filtered by date field and month.

    date_field can be 'opened_at' (default) or 'fulfilment_date'.
    Returns dict keyed by freshline_order_id.
    """
    orders = {}
    if not ORDERS_CSV.exists():
        print(f"ERROR: {ORDERS_CSV} not found. Run the daily sync first.")
        sys.exit(1)

    with open(ORDERS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = (row.get("state") or "").strip().lower()

            # Filter out cancelled (or apply explicit state filter)
            if include_states:
                if state not in include_states:
                    continue
            elif state in CANCELLED_STATES:
                continue

            # Filter by chosen date field
            if date_field == "fulfilment_date":
                fdate = row.get("fulfillment_date", "")
                if not (fdate and fdate >= month_start and fdate < month_end):
                    continue
            else:
                opened_at = row.get("opened_at_datetime", "")
                if not opened_at:
                    fdate = row.get("fulfillment_date", "")
                    if not (fdate and fdate >= month_start and fdate < month_end):
                        continue
                else:
                    opened_date = opened_at[:10]
                    if not (opened_date >= month_start and opened_date < month_end):
                        continue

            fl_id = row.get("freshline_order_id", "")
            if fl_id:
                orders[fl_id] = {
                    "order_number": row.get("order_number", ""),
                    "state": state,
                    "total": safe_float(row.get("total")),
                    "subtotal": safe_float(row.get("subtotal")),
                    "tax": safe_float(row.get("tax")),
                    "fulfillment_fee": safe_float(row.get("fulfillment_fee")),
                    "opened_at": row.get("opened_at_datetime", ""),
                }
    return orders


def query_notion_orders(
    notion: Client,
    month_start: str,
    month_end: str,
    date_field: str = "opened_at",
) -> dict:
    """Query Notion Orders data source for the given month.

    date_field can be 'opened_at' (default) or 'fulfilment_date'.
    Returns dict keyed by freshline_order_id.
    """
    notion_date_prop = "Fulfilment date" if date_field == "fulfilment_date" else "Opened at"
    orders = {}
    has_more = True
    start_cursor = None
    page_count = 0

    while has_more:
        kwargs = {
            "data_source_id": ORDERS_DATA_SOURCE_ID,
            "filter": {
                "and": [
                    {"property": notion_date_prop, "date": {"on_or_after": month_start}},
                    {"property": notion_date_prop, "date": {"before": month_end}},
                    {"property": "State", "select": {"does_not_equal": "cancelled"}},
                ]
            },
            "page_size": 100,
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        try:
            resp = notion.data_sources.query(**kwargs)
        except APIResponseError as e:
            if e.status == 429:
                retry_after = float(e.headers.get("Retry-After", 2)) if hasattr(e, "headers") else 2
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            raise

        for page in resp.get("results", []):
            props = page.get("properties", {})
            fl_id = extract_rich_text(props.get("Freshline order ID", {}))
            if not fl_id:
                continue

            order_num = extract_title(props.get("Order Title", {}))
            state = extract_select(props.get("State", {}))
            total = extract_number(props.get("Total", {}))
            subtotal = extract_number(props.get("Subtotal", {}))
            tax = extract_number(props.get("Tax", {}))
            fee = extract_number(props.get("Fulfilment fee", {}))
            opened_at = extract_date_start(props.get("Opened at", {}))

            orders[fl_id] = {
                "order_number": order_num,
                "notion_page_id": page["id"],
                "state": state,
                "total": total,
                "subtotal": subtotal,
                "tax": tax,
                "fulfillment_fee": fee,
                "opened_at": opened_at,
                "archived": page.get("archived", False),
            }
            page_count += 1

        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
        time.sleep(0.3)  # throttle

    print(f"  Fetched {page_count} orders from Notion")
    return orders


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
def reconcile(bq_orders: dict, notion_orders: dict, tolerance: float) -> dict:
    """Compare BQ and Notion order sets. Returns a structured report."""
    all_ids = set(bq_orders.keys()) | set(notion_orders.keys())

    bq_only = []       # In BQ but not Notion (missing from Notion)
    notion_only = []   # In Notion but not BQ (shouldn't happen, or deleted in FL)
    mismatches = []     # In both but totals differ
    matched = []        # In both and totals match

    bq_total = 0.0
    notion_total = 0.0

    for fl_id in sorted(all_ids):
        bq = bq_orders.get(fl_id)
        notion = notion_orders.get(fl_id)

        if bq and not notion:
            bq_only.append({
                "freshline_order_id": fl_id,
                "order_number": bq["order_number"],
                "bq_total": bq["total"],
                "state": bq["state"],
            })
            bq_total += bq["total"]
        elif notion and not bq:
            notion_only.append({
                "freshline_order_id": fl_id,
                "order_number": notion["order_number"],
                "notion_total": notion["total"],
                "state": notion["state"],
                "archived": notion.get("archived", False),
            })
            notion_total += notion["total"]
        else:
            bq_total += bq["total"]
            notion_total += notion["total"]
            delta = abs(bq["total"] - notion["total"])
            if delta > tolerance:
                mismatches.append({
                    "freshline_order_id": fl_id,
                    "order_number": bq["order_number"],
                    "bq_total": bq["total"],
                    "notion_total": notion["total"],
                    "delta": round(bq["total"] - notion["total"], 2),
                    "state": bq["state"],
                })
            else:
                matched.append(fl_id)

    return {
        "bq_order_count": len(bq_orders),
        "notion_order_count": len(notion_orders),
        "bq_total": round(bq_total, 2),
        "notion_total": round(notion_total, 2),
        "aggregate_delta": round(bq_total - notion_total, 2),
        "matched": len(matched),
        "mismatches": mismatches,
        "bq_only": bq_only,
        "notion_only": notion_only,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Reconcile BQ vs Notion order totals")
    parser.add_argument("--month", required=True, help="Month to reconcile (YYYY-MM)")
    parser.add_argument("--state", default=None, help="Comma-separated states to include (default: all non-cancelled)")
    parser.add_argument("--verbose", action="store_true", help="Show per-order details")
    parser.add_argument("--tolerance", type=float, default=0.01, help="AUD tolerance for mismatches (default: 0.01)")
    parser.add_argument("--json-out", default=None, help="Save full report to JSON file")
    parser.add_argument("--date-field", default="opened_at",
                        choices=["opened_at", "fulfilment_date"],
                        help="Date field for month filter (default: opened_at)")
    args = parser.parse_args()

    month_start, month_end = parse_month(args.month)
    include_states = set(s.strip().lower() for s in args.state.split(",")) if args.state else None

    # Load env and init Notion client
    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY not set. Add it to .env")
        sys.exit(1)
    notion = Client(auth=api_key)

    # Load BQ baseline
    print(f"Loading BQ baseline for {args.month} (date_field={args.date_field})...")
    bq_orders = load_bq_orders(month_start, month_end, include_states, args.date_field)
    print(f"  {len(bq_orders)} orders from BQ baseline")

    # Query Notion
    print(f"Querying Notion for {args.month} (date_field={args.date_field})...")
    notion_orders = query_notion_orders(notion, month_start, month_end, args.date_field)

    # Reconcile
    print("\nReconciling...")
    report = reconcile(bq_orders, notion_orders, args.tolerance)

    # Print report
    print(f"\n{'='*60}")
    print(f"RECONCILIATION REPORT — {args.month}")
    print(f"{'='*60}")
    print(f"  BQ orders:     {report['bq_order_count']:>6}   Total: A${report['bq_total']:>12,.2f}")
    print(f"  Notion orders: {report['notion_order_count']:>6}   Total: A${report['notion_total']:>12,.2f}")
    print(f"  Delta:                    A${report['aggregate_delta']:>12,.2f}")
    print()
    print(f"  Matched:       {report['matched']}")
    print(f"  Mismatches:    {len(report['mismatches'])}")
    print(f"  BQ only:       {len(report['bq_only'])}")
    print(f"  Notion only:   {len(report['notion_only'])}")

    if report["mismatches"]:
        print(f"\n--- Mismatches (tolerance: A${args.tolerance}) ---")
        for m in report["mismatches"]:
            print(f"  #{m['order_number']} (FL {m['freshline_order_id']}): "
                  f"BQ A${m['bq_total']:,.2f} vs Notion A${m['notion_total']:,.2f} "
                  f"(delta A${m['delta']:+,.2f}) [{m['state']}]")

    if report["bq_only"]:
        print(f"\n--- In BQ but NOT in Notion ---")
        for o in report["bq_only"]:
            print(f"  #{o['order_number']} (FL {o['freshline_order_id']}): "
                  f"A${o['bq_total']:,.2f} [{o['state']}]")

    if report["notion_only"]:
        print(f"\n--- In Notion but NOT in BQ ---")
        for o in report["notion_only"]:
            archived = " [ARCHIVED]" if o.get("archived") else ""
            print(f"  #{o['order_number']} (FL {o['freshline_order_id']}): "
                  f"A${o['notion_total']:,.2f} [{o['state']}]{archived}")

    if args.verbose and report["matched"]:
        print(f"\n--- Matched orders ({report['matched']}) ---")
        for fl_id in sorted(bq_orders.keys()):
            if fl_id in report.get("_matched_ids", set()):
                bq = bq_orders[fl_id]
                print(f"  #{bq['order_number']}: A${bq['total']:,.2f}")

    # Save JSON report
    if args.json_out:
        out_path = Path(args.json_out)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nFull report saved to {out_path}")

    print()


if __name__ == "__main__":
    main()
