#!/usr/bin/env python3
import csv

print("Sample of flattened activities (v2):\n")
print(f"{'ID':<20} {'Activity Name':<40} {'Contact IDs':<25} {'Contacts':<30} {'Accounts':<40}")
print("=" * 160)

with open('flattened_activities_v2.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 15:
            break
        contact_ids = row['links_contacts'] if row['links_contacts'] != 'NA' else ''
        print(f"{row['id']:<20} {row['name'][:40]:<40} {contact_ids[:25]:<25} {row['contact_names'][:30]:<30} {row['account_names'][:40]:<40}")

print("\n\nChecking coverage:")
with open('flattened_activities_v2.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    total = 0
    has_contacts = 0
    has_accounts = 0
    has_both = 0

    for row in reader:
        total += 1
        has_c = row['contact_names'] and row['contact_names'].strip()
        has_a = row['account_names'] and row['account_names'].strip()

        if has_c:
            has_contacts += 1
        if has_a:
            has_accounts += 1
        if has_c and has_a:
            has_both += 1

    print(f"Total activities: {total}")
    print(f"Activities with contact names: {has_contacts} ({has_contacts/total*100:.1f}%)")
    print(f"Activities with account names: {has_accounts} ({has_accounts/total*100:.1f}%)")
    print(f"Activities with both: {has_both} ({has_both/total*100:.1f}%)")
