"""
Deduplicate Notion Order Line Items created by a partial double-run of the
initial bulk import (8 Apr 2026).

For each Freshline line item ID with >1 Notion page, keeps the earliest page
(by created_time) and archives the rest.

Usage:
    python dedup_line_items.py --dry-run        # report only, no changes
    python dedup_line_items.py                  # archive duplicates
    python dedup_line_items.py --update-ids     # also fix existing-line-item-ids.json

Options:
    --dry-run       Show what would be archived without making changes
    --update-ids    Update existing-line-item-ids.json to point to kept pages
    --json-out FILE Save full report to JSON
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from notion_client import Client
from notion_client.errors import APIResponseError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
EXISTING_LI_PATH = SCRIPT_DIR / "existing-line-item-ids.json"

# Notion Line Items data source ID
LINE_ITEMS_DS_ID = "33c8094c-3d8a-8074-a5b3-000bc7dad468"


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


def extract_rich_text(prop: dict) -> str:
    """Extract plain text from a Notion rich_text property."""
    if not prop or prop.get("type") != "rich_text":
        return ""
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


# ---------------------------------------------------------------------------
# Fetch all line item pages
# ---------------------------------------------------------------------------
def fetch_all_line_items(notion: Client) -> list[dict]:
    """Paginate through all pages in the Line Items data source.

    Returns list of dicts with: page_id, created_time, fl_li_id.
    """
    pages = []
    has_more = True
    start_cursor = None
    batch = 0

    while has_more:
        kwargs = {
            "data_source_id": LINE_ITEMS_DS_ID,
            "page_size": 100,
            "filter_properties": ["Freshline line item ID"],
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        try:
            resp = notion.data_sources.query(**kwargs)
        except APIResponseError as e:
            if e.status == 429:
                retry_after = float(
                    e.headers.get("Retry-After", 2)
                ) if hasattr(e, "headers") else 2
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            raise

        for page in resp.get("results", []):
            props = page.get("properties", {})
            fl_li_id = extract_rich_text(props.get("Freshline line item ID", {}))
            pages.append({
                "page_id": page["id"],
                "created_time": page.get("created_time", ""),
                "fl_li_id": fl_li_id,
                "archived": page.get("archived", False),
            })

        batch += 1
        fetched = len(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")

        if batch % 5 == 0:
            print(f"  Fetched {len(pages)} pages so far...")
        time.sleep(0.35)

    print(f"  Total pages fetched: {len(pages)}")
    return pages


# ---------------------------------------------------------------------------
# Identify duplicates
# ---------------------------------------------------------------------------
def find_duplicates(pages: list[dict]) -> dict:
    """Group pages by FL LI ID, return groups with >1 non-archived page.

    Returns dict: fl_li_id -> {keep: page_dict, archive: [page_dicts]}
    """
    groups = defaultdict(list)
    for p in pages:
        if p["fl_li_id"] and not p["archived"]:
            groups[p["fl_li_id"]].append(p)

    duplicates = {}
    for fl_li_id, group in groups.items():
        if len(group) > 1:
            # Sort by created_time ascending — keep the earliest
            group.sort(key=lambda x: x["created_time"])
            duplicates[fl_li_id] = {
                "keep": group[0],
                "archive": group[1:],
            }

    return duplicates


# ---------------------------------------------------------------------------
# Archive duplicates
# ---------------------------------------------------------------------------
def archive_pages(notion: Client, duplicates: dict, dry_run: bool) -> dict:
    """Archive duplicate pages. Returns summary stats."""
    total_to_archive = sum(len(d["archive"]) for d in duplicates.values())
    archived_count = 0
    errors = []

    print(f"\n{'DRY RUN — ' if dry_run else ''}Archiving {total_to_archive} "
          f"duplicate pages across {len(duplicates)} FL line item IDs...\n")

    for fl_li_id, info in sorted(duplicates.items()):
        keep = info["keep"]
        for dup in info["archive"]:
            if dry_run:
                print(f"  [DRY RUN] Would archive {dup['page_id']} "
                      f"(created {dup['created_time']}) — "
                      f"keeping {keep['page_id']} (created {keep['created_time']})")
                archived_count += 1
                continue

            try:
                notion.pages.update(page_id=dup["page_id"], archived=True)
                archived_count += 1
                if archived_count % 25 == 0:
                    print(f"  Archived {archived_count}/{total_to_archive}...")
                time.sleep(0.35)
            except APIResponseError as e:
                if e.status == 429:
                    retry_after = float(
                        e.headers.get("Retry-After", 2)
                    ) if hasattr(e, "headers") else 2
                    print(f"  Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    try:
                        notion.pages.update(page_id=dup["page_id"], archived=True)
                        archived_count += 1
                    except Exception as e2:
                        errors.append({"page_id": dup["page_id"], "fl_li_id": fl_li_id, "error": str(e2)})
                else:
                    errors.append({"page_id": dup["page_id"], "fl_li_id": fl_li_id, "error": str(e)})
                    print(f"  ERROR archiving {dup['page_id']}: {e}")

    return {
        "total_to_archive": total_to_archive,
        "archived": archived_count,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Update existing-line-item-ids.json
# ---------------------------------------------------------------------------
def update_existing_ids(duplicates: dict):
    """Update the ID map so each FL LI ID points to the kept page."""
    if not EXISTING_LI_PATH.exists():
        print("  WARNING: existing-line-item-ids.json not found, skipping update")
        return

    with open(EXISTING_LI_PATH) as f:
        id_map = json.load(f)

    updated = 0
    for fl_li_id, info in duplicates.items():
        keep_page_id = info["keep"]["page_id"]
        if id_map.get(fl_li_id) != keep_page_id:
            id_map[fl_li_id] = keep_page_id
            updated += 1

    with open(EXISTING_LI_PATH, "w") as f:
        json.dump(id_map, f, indent=2)

    print(f"  Updated {updated} entries in existing-line-item-ids.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Deduplicate Notion line item pages")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    parser.add_argument("--update-ids", action="store_true",
                        help="Update existing-line-item-ids.json to point to kept pages")
    parser.add_argument("--json-out", default=None, help="Save report to JSON file")
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY not set. Add it to .env")
        sys.exit(1)

    notion = Client(auth=api_key)

    # Step 1: Fetch all line item pages
    print("Fetching all line item pages from Notion...")
    pages = fetch_all_line_items(notion)

    # Step 2: Find duplicates
    print("\nIdentifying duplicates...")
    duplicates = find_duplicates(pages)

    total_dupes = sum(len(d["archive"]) for d in duplicates.values())
    print(f"  Found {len(duplicates)} FL line item IDs with duplicates "
          f"({total_dupes} pages to archive)")

    if not duplicates:
        print("\nNo duplicates found. Nothing to do.")
        return

    # Print summary by creation time bucket
    early_batch = set()
    late_batch = set()
    for info in duplicates.values():
        early_batch.add(info["keep"]["created_time"][:16])
        for dup in info["archive"]:
            late_batch.add(dup["created_time"][:16])

    print(f"\n  Kept pages created at: {sorted(early_batch)}")
    print(f"  Dup pages created at:  {sorted(late_batch)}")

    # Step 3: Archive
    result = archive_pages(notion, duplicates, args.dry_run)

    # Step 4: Update ID map
    if args.update_ids and not args.dry_run:
        print("\nUpdating existing-line-item-ids.json...")
        update_existing_ids(duplicates)

    # Summary
    print(f"\n{'='*60}")
    print(f"DEDUP SUMMARY {'(DRY RUN)' if args.dry_run else ''}")
    print(f"{'='*60}")
    print(f"  Total pages scanned:     {len(pages)}")
    print(f"  FL LI IDs with dupes:    {len(duplicates)}")
    print(f"  Pages archived:          {result['archived']}")
    print(f"  Errors:                  {len(result['errors'])}")
    print()

    # Build report
    report = {
        "total_pages_scanned": len(pages),
        "duplicate_fl_li_ids": len(duplicates),
        "pages_archived": result["archived"],
        "errors": result["errors"],
        "duplicates": {
            fl_id: {
                "kept_page_id": info["keep"]["page_id"],
                "kept_created_time": info["keep"]["created_time"],
                "archived_pages": [
                    {"page_id": d["page_id"], "created_time": d["created_time"]}
                    for d in info["archive"]
                ],
            }
            for fl_id, info in duplicates.items()
        },
    }

    if args.json_out:
        out_path = Path(args.json_out)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  Report saved to {out_path}")


if __name__ == "__main__":
    main()
