# Freshline Order Data Updater

Apify actor that updates Freshline order custom data fields with CartonCloud sales order information. Called from a Zapier workflow when orders are created/updated in CartonCloud.

## What it does

Given a Freshline order URL and CartonCloud sales order details, this actor:

1. Logs into Freshline admin
2. Navigates to the order edit page
3. Writes a JSON payload to the order's custom data field
4. Saves the order

The custom data field is populated with:

```json
{
  "sales_order": {
    "id": "120",
    "uuid": "4405fc95-4742-4dc8-aba9-2e8660cf37be"
  }
}
```

## Input

```json
{
  "freshlineOrderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_01KFC8H4NRJH7HYKH4ZXF5EFKK/edit",
  "salesOrderId": "120",
  "salesOrderUuid": "4405fc95-4742-4dc8-aba9-2e8660cf37be"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `freshlineOrderUrl` | string | Yes | Full URL to the Freshline order edit page |
| `salesOrderId` | string | Yes | CartonCloud sales_order_id |
| `salesOrderUuid` | string | Yes | CartonCloud sales_order_uuid (UUID format) |

## Output

On success, the actor pushes to its dataset:

```json
{
  "success": true,
  "orderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx/edit",
  "salesOrderId": "120",
  "salesOrderUuid": "4405fc95-4742-4dc8-aba9-2e8660cf37be",
  "customDataJson": { "sales_order": { "id": "120", "uuid": "..." } },
  "timestamp": "2026-02-13T..."
}
```

On failure, it saves an error screenshot to the key-value store and pushes error details to the dataset.

## Setup

### Local development

1. Install dependencies:
   ```bash
   npm install
   ```

2. Create a `.env` file:
   ```
   FRESHLINE_USERNAME=your_email
   FRESHLINE_PASSWORD=your_password
   ```

3. Install the Apify CLI if you haven't:
   ```bash
   npm install -g apify-cli
   apify login
   ```

### Running locally

```bash
apify run --input-file test-input.json
```

## Deployment

1. Generate `package-lock.json` if missing:
   ```bash
   npm install
   ```

2. Push to Apify:
   ```bash
   apify push
   ```

3. Set environment variables in Apify Console:
   - Go to Actor settings > Environment variables
   - Add `FRESHLINE_USERNAME` with your email
   - Add `FRESHLINE_PASSWORD` with your password (mark as **Secret**)

4. Run a test from the Apify Console using the input format above.

## Zapier Integration

In your Zapier workflow, add a **Webhooks by Zapier** (or HTTP Request) action:

- **Method:** POST
- **URL:** `https://api.apify.com/v2/acts/<ACTOR_ID>/runs?token=<API_TOKEN>`
- **Body type:** JSON
- **Body:**
  ```json
  {
    "freshlineOrderUrl": "{{order_url_from_trigger}}",
    "salesOrderId": "{{cartoncloud_sales_order_id}}",
    "salesOrderUuid": "{{cartoncloud_sales_order_uuid}}"
  }
  ```

## Troubleshooting

| Problem | Solution |
|---|---|
| Login fails | Verify `FRESHLINE_USERNAME` and `FRESHLINE_PASSWORD` env vars are set correctly |
| Order form not found | Check the order URL is valid and the order exists. Look at the error screenshot in the key-value store. |
| Custom data field not found | The CSS selector in `src/main.js` may need updating. Inspect the Freshline order edit page to find the correct selector. |
| Save fails | Check the error screenshot. The page may have validation errors. |

### Viewing error screenshots

In the Apify Console, navigate to the actor run > Key-Value Store > `error-screenshot` to see the page state at the time of failure.

### Viewing logs

In the Apify Console, click on the actor run to see full logs with step-by-step progress.
