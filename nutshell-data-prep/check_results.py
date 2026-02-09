#!/usr/bin/env python3
import csv

print("Sample of flattened activities:\n")
print(f"{'ID':<20} {'Activity Name':<40} {'Participants':<30} {'Contacts':<30} {'Accounts':<40}")
print("=" * 160)

with open('flattened_activities.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 10:
            break
        print(f"{row['id']:<20} {row['name'][:40]:<40} {row['participants'][:30]:<30} {row['contact_names'][:30]:<30} {row['account_names'][:40]:<40}")
