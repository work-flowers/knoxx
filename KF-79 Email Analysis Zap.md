# KF-79: Analyse Incoming Emails to Orders Inbox

## Overview

This Zap monitors the Knoxx Foods orders inbox in Gmail and uses AI to classify whether each incoming email represents a customer order. It handles two paths depending on whether the email contains PDF attachments, and logs every result to a Zapier Table for review.

## Workflow

### 1. Trigger — New Email in Gmail

Watches the **Inbox** label for new messages. Timezone is set to Asia/Singapore.

### 2. Filter — Not from Internal Person

Two conditions (same group, so both must be true):

- **Stop** if the sender's email contains `@knoxxfoods.com` (filters out internal messages).
- **Continue** only if `thread_id` equals `message_id` (i.e. the message is the first in its thread, ignoring replies).

### 3. Paths (Branch)

Splits into two paths based on whether the email has PDF attachments.

---

#### Path A — Has PDF Attachments

**Step 4 (Filter):** Continues only when at least one attachment has MIME type containing `application/pdf`.

**Step 8 (Code — Identify PDFs):** Receives three comma-delimited arrays from the trigger (hydrated file objects, MIME types, and filenames) and filters to only the PDF items:

```javascript
const attachments = (inputData.attachments || "").split(",");
const mimeTypes = (inputData.mime_type || "").split(",");
const names = (inputData.attachment_name || "").split(",");

const pdfIndices = mimeTypes.reduce((acc, type, i) => {
  if (type.trim() === "application/pdf") acc.push(i);
  return acc;
}, []);

output = {
  attachments: pdfIndices.map((i) => attachments[i].trim()).join(","),
  mime_types: pdfIndices.map((i) => mimeTypes[i].trim()).join(","),
  attachment_names: pdfIndices.map((i) => names[i].trim()).join(","),
  count: pdfIndices.length,
};
```

**Step 9 (Google Drive — Upload File):** Uploads the filtered PDF attachment(s) to the **Order Attachments** folder in the Work.Flowers HQ shared drive.

**Step 10 (AI by Zapier — Analyse):** Sends the email body, sender name, sender email, and the uploaded Drive file to **GPT-5 mini** with instructions to evaluate whether the email represents a customer order. Returns structured output:

| Field | Type | Description |
|---|---|---|
| Email Summary | text | Summary of the email |
| Is Order Placed | boolean | Whether the email is an order |
| Justification | text | Reasoning behind the classification |

**Step 11 (Zapier Tables — Upsert Record):** Finds or creates a record in the **Orders Inbox Emails** table, keyed on Message ID. Writes: Message ID, From Name, From Email, Attachments, Body, Date, Is Order Placed, Justification, and Message URL.

---

#### Path B — Fallback (No PDF Attachments)

**Step 6 (AI by Zapier — Analyse):** Same AI analysis as Path A, but without an attachment input (only email body, sender name, and sender email).

**Step 7 (Zapier Tables — Upsert Record):** Same upsert to **Orders Inbox Emails**, but the Attachments field is left empty.

---

## Key Details

| Item | Value |
|---|---|
| Gmail account | Authenticated via OAuth (Knoxx orders inbox) |
| AI model | OpenAI GPT-5 mini (included in Zapier plan) |
| Drive destination | Work.Flowers HQ → Order Attachments |
| Table | Orders Inbox Emails |
| Dedup key | Gmail Message ID |

## Current State

The trigger (Step 1) is **active**. All subsequent steps (2–11) are **paused**, indicating the Zap is still being built/tested and has not been fully turned on yet.
