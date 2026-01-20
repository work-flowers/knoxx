# Freshline Line Item Updater

Apify actor that automates updating Freshline order line items with lot numbers and expiry dates from Carton Cloud.

## Overview

This actor logs into Freshline, navigates to an order edit page, matches line items by SKU, and updates the "Internal notes" (vendor_notes) field with lot numbers and best-before dates.

## Features

- Secure credential management via Apify environment variables
- Robust error handling with screenshot capture on failures
- Detailed logging for debugging
- Supports arbitrary numbers of line items per order
- SKU-based matching (independent of line item position)
- Comprehensive output data for verification

## Prerequisites

- Node.js 22+ (for local development)
- Apify account (free tier works for testing)
- Apify CLI (optional, for local development)
- Freshline credentials (username/password)

## Installation

### 1. Install Apify CLI (optional, for local development)

```bash
npm install -g apify-cli
```

### 2. Clone or Download This Repository

```bash
cd freshline-line-item-updater
```

### 3. Install Dependencies

```bash
npm install
```

## Configuration

### Environment Variables

The actor requires two environment variables for Freshline authentication:

- `FRESHLINE_USERNAME` - Your Freshline email address
- `FRESHLINE_PASSWORD` - Your Freshline password

#### Setting Environment Variables Locally

For local development, set these in your shell:

```bash
export FRESHLINE_USERNAME="your-email@example.com"
export FRESHLINE_PASSWORD="your-password"
```

Or create a `.env` file (not committed to git):

```bash
FRESHLINE_USERNAME=your-email@example.com
FRESHLINE_PASSWORD=your-password
```

#### Setting Environment Variables in Apify Cloud

1. Go to Apify Console → Your Actor → Settings → Environment Variables
2. Add `FRESHLINE_USERNAME` with your email
3. Add `FRESHLINE_PASSWORD` with your password
4. **Important**: Mark `FRESHLINE_PASSWORD` as "Secret" to encrypt it

## Input Format

The actor accepts JSON input with the following structure:

```json
{
  "freshlineOrderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx/edit",
  "lineItems": [
    {
      "sku": "RIC3001",
      "lot": "247",
      "expiry": "2028-09-03"
    },
    {
      "sku": "TOMC1005",
      "lot": "251",
      "expiry": "2027-06-15"
    }
  ]
}
```

### Parameters

- **freshlineOrderUrl** (string, required): Full URL to the Freshline order edit page
- **lineItems** (array, required): Array of objects with:
  - **sku** (string, required): Product SKU code to match (e.g., "RIC3001")
  - **lot** (string, required): Lot number to add to vendor notes
  - **expiry** (string, required): Best before date in YYYY-MM-DD format

## Running Locally

### Using Apify CLI

Create a test input file `test-input.json`:

```json
{
  "freshlineOrderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_01KFC8H4NRJH7HYKH4ZXF5EFKK/edit",
  "lineItems": [
    {
      "sku": "RIC3001",
      "lot": "247",
      "expiry": "2028-09-03"
    }
  ]
}
```

Run the actor:

```bash
apify run --input-file test-input.json
```

### Using Node.js Directly

```bash
node src/main.js
```

Note: When running directly with Node.js, you'll need to provide input via stdin or modify the script to read from a file.

## Deploying to Apify Cloud

### 1. Login to Apify

```bash
apify login
```

### 2. Deploy the Actor

```bash
apify push
```

This will:
- Build the Docker container
- Upload the actor to your Apify account
- Make it available for running in the cloud

### 3. Configure Environment Variables

1. Go to Apify Console
2. Navigate to your deployed actor
3. Click "Settings" → "Environment Variables"
4. Add `FRESHLINE_USERNAME` and `FRESHLINE_PASSWORD` (mark password as secret)

### 4. Test Run from Console

1. Go to your actor page in Apify Console
2. Click "Run"
3. Enter test input in JSON format
4. Click "Start"
5. Monitor the log output
6. Check the dataset for results

## Output Format

The actor saves results to the Apify dataset with the following structure:

```json
{
  "success": true,
  "orderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx/edit",
  "lineItemsProcessed": 2,
  "lineItemsUpdated": 2,
  "notFoundSkus": [],
  "updateDetails": [
    {
      "sku": "RIC3001",
      "lot": "247",
      "expiry": "2028-09-03",
      "success": true
    },
    {
      "sku": "TOMC1005",
      "lot": "251",
      "expiry": "2027-06-15",
      "success": true
    }
  ],
  "timestamp": "2026-01-20T12:34:56.789Z"
}
```

### Output Fields

- **success** (boolean): Whether the operation completed successfully
- **orderUrl** (string): The Freshline order URL that was processed
- **lineItemsProcessed** (number): Total number of line items in the input
- **lineItemsUpdated** (number): Number of line items successfully updated
- **notFoundSkus** (array): List of SKUs that were not found on the page
- **updateDetails** (array): Detailed results for each line item
- **timestamp** (string): ISO 8601 timestamp of when the operation completed

### Error Output

If the actor fails, the output will include error details:

```json
{
  "success": false,
  "error": "Login failed: Invalid credentials",
  "orderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx/edit",
  "timestamp": "2026-01-20T12:34:56.789Z"
}
```

Additionally, a screenshot is saved to the key-value store as `error-screenshot` for debugging.

## Zapier Integration

### Option 1: Using Apify's Native Zapier Integration

1. In Zapier, search for "Apify" and add a new action
2. Choose "Run Actor"
3. Select your deployed actor
4. Map the input fields:
   - `freshlineOrderUrl` → URL from your Zapier trigger
   - `lineItems` → JSON array from previous steps

### Option 2: Using Webhooks by Zapier

Make an HTTP POST request to Apify's API:

```
POST https://api.apify.com/v2/acts/YOUR_ACTOR_ID/runs?token=YOUR_APIFY_TOKEN
Content-Type: application/json

{
  "freshlineOrderUrl": "{{freshlineOrderUrl}}",
  "lineItems": {{lineItemsJson}}
}
```

Replace:
- `YOUR_ACTOR_ID`: Your actor's ID from Apify Console
- `YOUR_APIFY_TOKEN`: Your Apify API token (found in Settings)

## How It Works

1. **Login**: The actor navigates to the Freshline login page and authenticates using provided credentials
2. **Navigate**: Goes to the specified order edit page
3. **Match SKUs**: Finds all line items on the page and extracts their SKU codes from `<span class="font-mono">` elements
4. **Update Notes**: For each input line item, finds the matching SKU on the page and updates the corresponding vendor_notes textarea
5. **Save**: Clicks the "Save" button to persist changes
6. **Report**: Saves detailed results to the Apify dataset

## Troubleshooting

### Login Fails

- Verify `FRESHLINE_USERNAME` and `FRESHLINE_PASSWORD` are set correctly
- Check that the credentials work when logging in manually
- Look for error messages in the actor logs

### SKUs Not Found

- Verify the SKU codes in your input match exactly what appears on the Freshline order page (case-sensitive)
- Check that the order URL is correct and points to an order edit page
- Look at the `notFoundSkus` array in the output to see which SKUs couldn't be matched

### Save Button Not Clicked

- The actor looks for a button with text "Save" within the form
- If Freshline's UI changes, the selector may need updating
- Check the error screenshot in the key-value store to see the page state

### Screenshot Location

When an error occurs, a screenshot is saved to the Apify key-value store. To view it:

1. Go to Apify Console → Your Actor Run
2. Click "Storage" → "Key-value store"
3. Look for `error-screenshot`
4. Click to download and view

## Development

### Project Structure

```
freshline-line-item-updater/
├── .actor/
│   └── actor.json          # Apify actor configuration
├── src/
│   └── main.js            # Main actor code
├── .gitignore             # Git ignore file
├── Dockerfile             # Container definition
├── INPUT_SCHEMA.json      # Input validation schema
├── package.json           # Node.js dependencies
└── README.md              # This file
```

### Key Dependencies

- **apify**: Apify SDK for actor development
- **crawlee**: Web scraping and crawling library (includes Puppeteer support)

### Modifying Selectors

If Freshline changes their HTML structure, you may need to update selectors in `src/main.js`:

- **Login email field**: `#staff_email` (line 43)
- **Login password field**: `#staff_password` (line 44)
- **Login button**: `button[type="submit"]` (line 51)
- **Line items container**: `#line-items` (line 70)
- **SKU element**: `span.font-mono` (line 89)
- **Vendor notes textarea**: `#${liId}_vendor_notes` (line 105)
- **Save button**: `button:has-text("Save")` or fallback (line 141)

## Known Limitations

1. **Selector brittleness**: If Freshline changes their HTML structure, selectors may break
2. **No verification**: Doesn't re-read the page after saving to confirm updates persisted
3. **Single order only**: Can't batch process multiple orders in one run
4. **No rollback**: Once saved, changes can't be automatically undone
5. **Duplicate SKUs**: If the same SKU appears multiple times on a page, only the first match is updated

## Future Enhancements

- [ ] Batch processing for multiple orders
- [ ] Dry run mode for testing without saving
- [ ] Post-save verification step
- [ ] Retry logic for transient failures
- [ ] Session reuse for better performance
- [ ] Webhook notifications on completion/failure

## Support

For issues or questions:
- Check the Apify actor logs for detailed error messages
- Review the error screenshot in the key-value store
- Verify all environment variables are set correctly
- Test with a simple order (1-2 line items) first

## License

MIT

## Related Documentation

- [Apify Documentation](https://docs.apify.com/)
- [Crawlee Documentation](https://crawlee.dev/)
- [Puppeteer Documentation](https://pptr.dev/)
