#!/usr/bin/env python3
"""
Flatten Nutshell activities with associated contacts and accounts.
Combines data from both activities files to get all columns.
"""

import csv

# Read accounts and create lookup
print("Reading accounts...")
account_lookup = {}
with open('Accounts.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        account_lookup[row['id']] = row['name']

print(f"Loaded {len(account_lookup)} accounts")

# Read contacts and create lookups
print("Reading contacts...")
contact_lookup = {}
contact_id_to_accounts = {}
with open('Contacts.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        contact_lookup[row['id']] = row['name']
        contact_id_to_accounts[row['id']] = row['accounts']

print(f"Loaded {len(contact_lookup)} contacts")

# Read original Activities.csv and create lookup for additional columns
print("Reading original Activities.csv for additional columns...")
original_activities = {}
with open('Activities.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        original_activities[row['id']] = row

print(f"Loaded {len(original_activities)} original activity records")

# Function to get contact and account names from IDs
def get_names_from_ids(contact_ids_str, account_ids_str):
    contact_names = []
    account_names_from_contacts = set()
    direct_account_names = set()

    # Process contact IDs
    if contact_ids_str and contact_ids_str.strip() and contact_ids_str != 'NA':
        contact_ids = [cid.strip() for cid in contact_ids_str.split(',')]

        for contact_id in contact_ids:
            if contact_id:
                # Get contact name
                contact_name = contact_lookup.get(contact_id)
                if contact_name:
                    contact_names.append(contact_name)

                # Get accounts associated with this contact
                contact_account_ids_str = contact_id_to_accounts.get(contact_id, '')
                if contact_account_ids_str and contact_account_ids_str.strip():
                    contact_account_ids = [aid.strip() for aid in contact_account_ids_str.split(',')]
                    for account_id in contact_account_ids:
                        account_name = account_lookup.get(account_id)
                        if account_name:
                            account_names_from_contacts.add(account_name)

    # Process direct account IDs (from links_accounts)
    if account_ids_str and account_ids_str.strip() and account_ids_str != 'NA':
        account_ids = [aid.strip() for aid in account_ids_str.split(',')]

        for account_id in account_ids:
            if account_id:
                account_name = account_lookup.get(account_id)
                if account_name:
                    direct_account_names.add(account_name)

    # Combine all account names (from both contacts and direct links)
    all_account_names = account_names_from_contacts.union(direct_account_names)

    return ', '.join(contact_names), ', '.join(sorted(all_account_names))

# Process activities
print("Processing activities and merging data...")
input_file = 'nutshell_activities_20260122_132323.csv'
output_file = 'flattened_activities_complete.csv'
activity_count = 0

with open(input_file, 'r', encoding='utf-8-sig') as infile, \
     open(output_file, 'w', newline='', encoding='utf-8') as outfile:

    reader = csv.DictReader(infile)

    # Define output columns: all from new file + selected from old file + our new columns
    # Note: we'll rename 'type' from nutshell file to 'record_type' and add 'activity_type' from Activities.csv
    base_fieldnames = [f if f != 'type' else 'record_type' for f in reader.fieldnames]

    fieldnames = base_fieldnames + [
        'activity_type',
        'creator',
        'created_time',
        'status',
        'is_all_day',
        'is_flagged',
        'is_timed',
        'description',
        'participants',
        'leads',
        'note',
        'follow_up_activity_id',
        'contact_names',
        'account_names'
    ]

    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        activity_count += 1
        activity_id = row['id']

        # Rename 'type' to 'record_type'
        if 'type' in row:
            row['record_type'] = row.pop('type')

        # Get contact and account names
        contact_ids = row.get('links_contacts', '')
        account_ids = row.get('links_accounts', '')
        contact_names, account_names = get_names_from_ids(contact_ids, account_ids)

        # Add new columns
        row['contact_names'] = contact_names
        row['account_names'] = account_names

        # Merge in columns from original Activities.csv if available
        if activity_id in original_activities:
            orig = original_activities[activity_id]
            row['activity_type'] = orig.get('type', '')
            row['creator'] = orig.get('creator', '')
            row['created_time'] = orig.get('created_time', '')
            row['status'] = orig.get('status', '')
            row['is_all_day'] = orig.get('is_all_day', '')
            row['is_flagged'] = orig.get('is_flagged', '')
            row['is_timed'] = orig.get('is_timed', '')
            row['description'] = orig.get('description', '')
            row['participants'] = orig.get('participants', '')
            row['leads'] = orig.get('leads', '')
            row['note'] = orig.get('note', '')
            row['follow_up_activity_id'] = orig.get('follow_up_activity_id', '')
        else:
            # Fill with empty values if not found
            row['activity_type'] = ''
            row['creator'] = ''
            row['created_time'] = ''
            row['status'] = ''
            row['is_all_day'] = ''
            row['is_flagged'] = ''
            row['is_timed'] = ''
            row['description'] = ''
            row['participants'] = ''
            row['leads'] = ''
            row['note'] = ''
            row['follow_up_activity_id'] = ''

        writer.writerow(row)

print(f"\nComplete flattened activities saved to: {output_file}")
print(f"Total activities processed: {activity_count}")
print("\nThe file includes:")
print("  - All columns from nutshell_activities_20260122_132323.csv")
print("    (with 'type' renamed to 'record_type')")
print("  - Additional columns from Activities.csv:")
print("    * activity_type (Phone Call, Meeting, etc.)")
print("    * creator, created_time, status, etc.")
print("  - contact_names: comma-separated list of contact names")
print("  - account_names: comma-separated list of account names")
