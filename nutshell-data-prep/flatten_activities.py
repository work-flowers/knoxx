#!/usr/bin/env python3
"""
Flatten Nutshell activities with associated contacts and accounts.
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
contact_name_to_id = {}
contact_id_to_accounts = {}
with open('Contacts.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        contact_name_to_id[row['name']] = row['id']
        contact_id_to_accounts[row['id']] = row['accounts']

print(f"Loaded {len(contact_name_to_id)} contacts")

# Function to get contact and account info
def get_contact_and_account_info(participants_str):
    if not participants_str or participants_str.strip() == '':
        return '', ''

    # Split participants by comma
    participant_names = [name.strip() for name in participants_str.split(',')]

    contact_names = []
    account_names_set = set()

    for participant_name in participant_names:
        if participant_name:
            contact_names.append(participant_name)

            # Get contact ID
            contact_id = contact_name_to_id.get(participant_name)

            if contact_id:
                # Get account IDs for this contact
                account_ids_str = contact_id_to_accounts.get(contact_id, '')

                if account_ids_str and account_ids_str.strip():
                    # Split account IDs (they're comma-separated)
                    account_ids = [aid.strip() for aid in account_ids_str.split(',')]

                    # Get account names
                    for account_id in account_ids:
                        account_name = account_lookup.get(account_id)
                        if account_name:
                            account_names_set.add(account_name)

    return ', '.join(contact_names), ', '.join(sorted(account_names_set))

# Process activities
print("Processing activities...")
output_file = 'flattened_activities.csv'
activity_count = 0

with open('Activities.csv', 'r', encoding='utf-8-sig') as infile, \
     open(output_file, 'w', newline='', encoding='utf-8') as outfile:

    reader = csv.DictReader(infile)

    # Get original fieldnames and add new columns
    fieldnames = reader.fieldnames + ['contact_names', 'account_names']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        activity_count += 1
        participants = row.get('participants', '')
        contact_names, account_names = get_contact_and_account_info(participants)

        row['contact_names'] = contact_names
        row['account_names'] = account_names

        writer.writerow(row)

print(f"\nFlattened activities saved to: {output_file}")
print(f"Total activities processed: {activity_count}")
print("\nDone! The file now has two additional columns:")
print("  - contact_names: comma-separated list of contact names")
print("  - account_names: comma-separated list of account names")
