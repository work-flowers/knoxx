# CartonCloud Order Attachment

Apify actor that attaches files to CartonCloud sales order documents from provided URLs. Called from a Zapier automation that passes file URLs and a CartonCloud Add Document page URL.

## What it does

Given a CartonCloud Add Document URL and one or more file URLs, this actor:

1. Downloads files from the provided URLs
2. Logs into CartonCloud
3. Navigates to the Add Document page
4. Sets the document Name and optional Description
5. Uploads the files via the attachment drop zone
6. Clicks Save
7. Reports success/failure

## Input

```json
{
  "cartonCloudDocumentUrl": "https://app.cartoncloud.com/Knoxx_Foods/outbound-orders/{id}/documents/add",
  "files": [
    "https://example.com/invoice.pdf",
    "https://example.com/photo.png"
  ],
  "names": [
    "Invoice-2026-001.pdf",
    "Product Photo.png"
  ],
  "documentName": "Packing Confirmation",
  "description": "Attached by automation"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `cartonCloudDocumentUrl` | string | Yes | Full URL to the CartonCloud Add Document page |
| `files` | string or string[] | Yes | Array or comma-separated list of public URLs to files to download and attach |
| `names` | string or string[] | No | Array or comma-separated list of filenames, matched by position to file URLs. If omitted, filenames are derived from the URLs. |
| `documentName` | string | No | "Packing Confirmation" (default) or "Other" |
| `description` | string | No | Optional text to enter in the Description field |

## Output

On success:

```json
{
  "success": true,
  "documentUrl": "https://app.cartoncloud.com/Knoxx_Foods/outbound-orders/.../documents/add",
  "filesUploaded": 2,
  "documentName": "Packing Confirmation",
  "timestamp": "2026-03-03T..."
}
```

On failure, an error screenshot is saved to the key-value store and error details are pushed to the dataset.

## Setup

### Local development

1. Install dependencies:
   ```bash
   npm install
   ```

2. Create a `.env` file:
   ```
   CARTONCLOUD_USERNAME=your_email
   CARTONCLOUD_PASSWORD=your_password
   ```

3. Install Apify CLI if needed:
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
   - Add `CARTONCLOUD_USERNAME` with your email
   - Add `CARTONCLOUD_PASSWORD` with your password (mark as **Secret**)

## Zapier Integration

In your Zapier workflow, add a **Webhooks by Zapier** action:

- **Method:** POST
- **URL:** `https://api.apify.com/v2/acts/<ACTOR_ID>/runs?token=<API_TOKEN>`
- **Body type:** JSON
- **Body:**
  ```json
  {
    "cartonCloudDocumentUrl": "{{document_add_url}}",
    "files": "{{file_url_1}}, {{file_url_2}}",
    "names": "{{file_name_1}}, {{file_name_2}}",
    "documentName": "Packing Confirmation",
    "description": "{{description}}"
  }
  ```

## Troubleshooting

| Problem | Solution |
|---|---|
| Login fails | Verify `CARTONCLOUD_USERNAME` and `CARTONCLOUD_PASSWORD` env vars |
| File download fails | Check that file URLs are publicly accessible |
| File input not found | The page structure may have changed. Inspect for `input[data-testid="file-input"]`. |
| Save button not found | Look for `button[data-testid="save-button"]` on the page. |
| Name dropdown not working | The dropdown may have changed. Inspect the Name field on the Add Document page. |

### Viewing error screenshots

In the Apify Console, navigate to the actor run > Key-Value Store > `error-screenshot`.
