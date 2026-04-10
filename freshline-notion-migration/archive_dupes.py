"""
Archive duplicate line item pages identified by dedup_line_items.py dry run.

Reads dedup-report-dry-run.json and archives pages in batches, saving progress
so it can resume if interrupted.

Usage:
    python archive_dupes.py [--batch-size 50]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from notion_client import Client
from notion_client.errors import APIResponseError

SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
REPORT_PATH = SCRIPT_DIR / "dedup-report-dry-run.json"
PROGRESS_PATH = SCRIPT_DIR / "dedup-archive-progress.json"
EXISTING_LI_PATH = SCRIPT_DIR / "existing-line-item-ids.json"


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=80,
                        help="Pages to archive per run (default 80)")
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY not set")
        sys.exit(1)

    notion = Client(auth=api_key)

    # Load report
    with open(REPORT_PATH) as f:
        report = json.load(f)

    # Build flat list of pages to archive
    all_to_archive = []
    kept_map = {}  # fl_li_id -> kept_page_id
    for fl_li_id, info in report["duplicates"].items():
        kept_map[fl_li_id] = info["kept_page_id"]
        for ap in info["archived_pages"]:
            all_to_archive.append({
                "page_id": ap["page_id"],
                "fl_li_id": fl_li_id,
                "created_time": ap["created_time"],
            })

    # Load progress (already archived page IDs)
    archived_ids = set()
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            progress = json.load(f)
            archived_ids = set(progress.get("archived_page_ids", []))

    remaining = [p for p in all_to_archive if p["page_id"] not in archived_ids]
    batch = remaining[:args.batch_size]

    print(f"Total to archive: {len(all_to_archive)}")
    print(f"Already archived: {len(archived_ids)}")
    print(f"Remaining:        {len(remaining)}")
    print(f"This batch:       {len(batch)}")
    print()

    errors = []
    for i, item in enumerate(batch):
        try:
            notion.pages.update(page_id=item["page_id"], archived=True)
            archived_ids.add(item["page_id"])
            if (i + 1) % 20 == 0:
                print(f"  Archived {i + 1}/{len(batch)}...")
        except APIResponseError as e:
            if e.status == 429:
                retry_after = float(
                    e.headers.get("Retry-After", 2)
                ) if hasattr(e, "headers") else 2
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                try:
                    notion.pages.update(page_id=item["page_id"], archived=True)
                    archived_ids.add(item["page_id"])
                except Exception as e2:
                    errors.append({"page_id": item["page_id"], "error": str(e2)})
            elif "archived" in str(e).lower():
                # Already archived (e.g. by a previous run) — count as success
                archived_ids.add(item["page_id"])
            else:
                errors.append({"page_id": item["page_id"], "error": str(e)})
                print(f"  ERROR {item['page_id']}: {e}")
        time.sleep(0.35)

    # Save progress
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"archived_page_ids": list(archived_ids)}, f)

    new_remaining = len(all_to_archive) - len(archived_ids)
    print(f"\nBatch complete: archived {len(batch) - len(errors)} pages")
    print(f"Errors: {len(errors)}")
    print(f"Remaining: {new_remaining}")

    # If all done, update existing-line-item-ids.json
    if new_remaining == 0:
        print("\nAll duplicates archived! Updating existing-line-item-ids.json...")
        if EXISTING_LI_PATH.exists():
            with open(EXISTING_LI_PATH) as f:
                id_map = json.load(f)
            updated = 0
            for fl_li_id, kept_page_id in kept_map.items():
                if id_map.get(fl_li_id) != kept_page_id:
                    id_map[fl_li_id] = kept_page_id
                    updated += 1
            with open(EXISTING_LI_PATH, "w") as f:
                json.dump(id_map, f, indent=2)
            print(f"  Updated {updated} entries in existing-line-item-ids.json")
        print("\nDONE — all duplicates archived and ID map updated.")
    else:
        print(f"\nRun again to archive the next batch ({new_remaining} remaining)")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['page_id']}: {e['error']}")


if __name__ == "__main__":
    main()
