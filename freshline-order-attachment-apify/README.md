# Freshline Order Attachment

Apify actor that attaches files to Freshline orders from provided URLs. Called from a Zapier automation that passes file URLs and a Freshline order URL.

## What it does

Given a Freshline order URL and one or more file URLs, this actor:

1. Downloads files from the provided URLs
2. Logs into Freshline admin
3. Navigates to the order view page
4. Uploads the files via the "Upload attachment" section
5. Reports success/failure

## Input

```json
{
  "freshlineOrderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx",
  "files": [
    "https://example.com/invoice.pdf",
    "https://example.com/photo.png"
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `freshlineOrderUrl` | string | Yes | URL to the Freshline order (view or edit — `/edit` is stripped automatically) |
| `files` | string[] | Yes | Array of public URLs to files to download and attach |

**Supported file types:** PDF, DOC, DOCX, XLS, XLSX, TXT, CSV, JPG, JPEG, PNG, GIF, WEBP, AVIF, HEIC

## Output

On success:

```json
{
  "success": true,
  "orderUrl": "https://my.knoxxfoods.com/admin/orders/ordr_xxx",
  "filesUploaded": 2,
  "fileUrls": ["https://...", "https://..."],
  "timestamp": "2026-03-02T..."
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
   FRESHLINE_USERNAME=your_email
   FRESHLINE_PASSWORD=your_password
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
   - Add `FRESHLINE_USERNAME` with your email
   - Add `FRESHLINE_PASSWORD` with your password (mark as **Secret**)

## Zapier Integration

In your Zapier workflow, add a **Webhooks by Zapier** action:

- **Method:** POST
- **URL:** `https://api.apify.com/v2/acts/<ACTOR_ID>/runs?token=<API_TOKEN>`
- **Body type:** JSON
- **Body:**
  ```json
  {
    "freshlineOrderUrl": "{{order_url}}",
    "files": ["{{file_url_1}}", "{{file_url_2}}"]
  }
  ```

## Troubleshooting

| Problem | Solution |
|---|---|
| Login fails | Verify `FRESHLINE_USERNAME` and `FRESHLINE_PASSWORD` env vars |
| File download fails | Check that file URLs are publicly accessible |
| File input not found | The order view page structure may have changed. Inspect for `input[name="attachment_file"]`. |
| Upload button not found | Look for `button[type="submit"]` with text "Upload" on the page. |

### Viewing error screenshots

In the Apify Console, navigate to the actor run > Key-Value Store > `error-screenshot`.
