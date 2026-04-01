import 'dotenv/config';
import { Actor } from 'apify';
import { PuppeteerCrawler, log } from 'crawlee';
import { writeFile, unlink } from 'node:fs/promises';
import { basename } from 'node:path';

await Actor.init();

// Get input from Apify (from Zapier webhook or manual run)
const input = await Actor.getInput();

// Validate input
if (!input?.freshlineOrderUrl || !input?.files) {
    throw new Error('Invalid input: freshlineOrderUrl and files are required');
}

// Accept files as either an array or a comma-separated string
const rawFiles = Array.isArray(input.files)
    ? input.files
    : input.files.split(',').map(s => s.trim()).filter(Boolean);

if (rawFiles.length === 0) {
    throw new Error('Invalid input: files must contain at least one URL');
}

// Accept names as either an array or a comma-separated string (optional)
const rawNames = input.names
    ? (Array.isArray(input.names)
        ? input.names
        : input.names.split(',').map(s => s.trim()))
    : [];

// Pair URLs with names by index — name is null if not provided
const files = rawFiles.map((url, i) => ({
    url: url.trim(),
    name: rawNames[i]?.trim() || null,
}));

// Ensure we use the order view URL (not edit) — attachments are on the view page
const freshlineOrderUrl = input.freshlineOrderUrl.replace(/\/edit\/?$/, '');

// Get credentials from environment variables
const username = process.env.FRESHLINE_USERNAME;
const password = process.env.FRESHLINE_PASSWORD;

if (!username || !password) {
    throw new Error('Missing credentials: FRESHLINE_USERNAME and FRESHLINE_PASSWORD environment variables must be set');
}

log.info('Starting Freshline Order Attachment', {
    orderUrl: freshlineOrderUrl,
    fileCount: files.length,
});

// Download a file from URL to /tmp/ with optional custom name
async function downloadFile(url, customName) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
    }

    const buffer = Buffer.from(await response.arrayBuffer());

    // Use custom name if provided, otherwise derive from URL.
    // Zapier can pass the literal strings "null" or "undefined" when a field is empty.
    const invalidNames = new Set(['null', 'undefined', '']);
    let filename = (!customName || invalidNames.has(customName.toLowerCase()))
        ? decodeURIComponent(basename(new URL(url).pathname)) || 'attachment'
        : customName;

    // Sanitise unsafe path characters (e.g. slashes in date strings like "23/03/2026")
    filename = filename.replace(/[/\\:*?"<>|]/g, '-');

    const filepath = `/tmp/${filename}`;
    await writeFile(filepath, buffer);
    log.info(`Downloaded: ${filename} (${buffer.length} bytes)`);
    return { filepath, bytes: buffer.length };
}

// Download all files before starting the browser
log.info('Downloading files...');
const downloadedPaths = [];
let totalBytes = 0;
for (const { url, name } of files) {
    const { filepath, bytes } = await downloadFile(url, name);
    downloadedPaths.push(filepath);
    totalBytes += bytes;
}
log.info(`All ${downloadedPaths.length} files downloaded (${Math.round(totalBytes / 1024)} KB total)`);

// Create Puppeteer crawler
const crawler = new PuppeteerCrawler({
    headless: true,
    launchContext: {
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ],
        },
    },

    async requestHandler({ page, log }) {
        try {
            // Step 1: Login to Freshline
            log.info('Navigating to Freshline login page...');
            await page.goto('https://my.knoxxfoods.com/admin/login', {
                waitUntil: 'networkidle2',
                timeout: 30000,
            });

            await page.waitForSelector('#staff_email', { timeout: 10000 });
            log.info('Login page loaded');

            await page.type('#staff_email', username);
            await page.type('#staff_password', password);
            log.info('Credentials entered');

            await page.focus('#staff_password');
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
                page.keyboard.press('Enter'),
            ]);

            log.info('Form submitted');

            // Wait for any redirects to complete
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Check for login errors
            const loginError = await page.$('.error-message, .alert-error');
            if (loginError) {
                const errorText = await page.evaluate(el => el.textContent, loginError);
                throw new Error(`Login failed: ${errorText}`);
            }

            const currentUrl = page.url();
            if (currentUrl.includes('/login')) {
                throw new Error('Still on login page after attempting login. Check credentials.');
            }

            log.info('Login successful', { currentUrl });

            // Step 2: Navigate to the order view page
            log.info(`Navigating to order: ${freshlineOrderUrl}`);
            await page.goto(freshlineOrderUrl, {
                waitUntil: 'domcontentloaded',
                timeout: 60000,
            });

            // Phoenix LiveView initialization delay
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Scroll down to the upload section
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Step 3: Upload files using file chooser interception
            // Phoenix LiveView's LiveFileUpload hook requires trusted browser events.
            // We simulate the real user flow: click "Add attachments" → file dialog → select files.
            const fileInput = await page.$('input[name="attachment_file"]');
            if (!fileInput) {
                throw new Error('File input (input[name="attachment_file"]) not found on page');
            }

            log.info('File input found, triggering file chooser...');

            // Set up file chooser interception BEFORE clicking
            const fileChooserPromise = page.waitForFileChooser({ timeout: 10000 });

            // Click the "Add attachments" label to open the native file picker
            await page.evaluate(() => {
                const spans = document.querySelectorAll('span');
                for (const span of spans) {
                    if (span.textContent.trim() === 'Add attachments') {
                        span.click();
                        return;
                    }
                }
            });

            // Accept the file chooser with our downloaded files
            const fileChooser = await fileChooserPromise;
            await fileChooser.accept(downloadedPaths);
            log.info('Files accepted via file chooser');

            // Wait for LiveView to upload the file(s) via websocket.
            // The UI provides no visual completion indicator — the Upload button stays enabled
            // and the Cancel button stays visible throughout. So we estimate the wait time
            // based on total file size, assuming a conservative 500 KB/s upload speed with 2x safety margin.
            const totalMB = totalBytes / (1024 * 1024);
            const waitSeconds = Math.max(10, Math.ceil(totalMB / 0.5 * 2));
            const waitMs = Math.min(waitSeconds * 1000, 120000);
            log.info(`Waiting ${waitSeconds}s for file transfer (~${totalMB.toFixed(1)} MB at conservative rate)...`);
            await new Promise(resolve => setTimeout(resolve, waitMs));
            log.info('File transfer wait complete');

            log.info('File upload wait complete, clicking Upload button...');

            // Step 4: Click the Upload button to submit the form
            const uploadClicked = await page.evaluate(() => {
                const buttons = document.querySelectorAll('button[type="submit"]');
                for (const button of buttons) {
                    if (button.textContent.trim() === 'Upload') {
                        button.click();
                        return true;
                    }
                }
                return false;
            });

            if (!uploadClicked) {
                throw new Error('Could not find Upload button');
            }

            log.info('Upload button clicked, waiting for save...');

            // Wait for the form submission to complete
            await new Promise(resolve => setTimeout(resolve, 5000));

            log.info('Upload button submitted, verifying attachments...');

            // Step 5: Post-upload verification
            // Scroll to the attachments section and wait for LiveView to re-render
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Collect the filenames we expect to find (derive same way as downloadFile)
            const expectedNames = files.map(({ url: fileUrl, name }) => {
                const _invalidNames = new Set(['null', 'undefined', '']);
                const resolved = (!name || _invalidNames.has(name.toLowerCase()))
                    ? decodeURIComponent(basename(new URL(fileUrl).pathname)) || 'attachment'
                    : name;
                return resolved.replace(/[/\\:*?"<>|]/g, '-');
            });

            // Query the page for attachment links/items
            const attachmentNames = await page.evaluate(() => {
                // Look for links or list items inside the attachments container
                const container = document.querySelector('[id*="attachment"], [class*="attachment"], [data-phx-component]');
                if (!container) return [];
                const links = container.querySelectorAll('a, li');
                return Array.from(links).map(el => el.textContent.trim()).filter(Boolean);
            });

            log.info('Attachments found on page', { attachmentNames, expectedNames });

            // Check whether each expected file appears in the attachment list
            const missing = expectedNames.filter(
                name => !attachmentNames.some(a => a.includes(name))
            );

            let uploadVerified = missing.length === 0;

            if (!uploadVerified) {
                log.warning('Upload verification failed — expected file(s) not found in attachments list', { missing });
                try {
                    const verifyScreenshot = await page.screenshot({ fullPage: true });
                    await Actor.setValue('upload-verification-screenshot', verifyScreenshot, { contentType: 'image/png' });
                    log.info('Verification screenshot saved as "upload-verification-screenshot"');
                } catch (screenshotError) {
                    log.error(`Failed to capture verification screenshot: ${screenshotError.message}`);
                }
            } else {
                log.info('Upload verified — all expected files found in attachments list');
            }

            // Step 6: Store results
            const result = {
                success: uploadVerified,
                orderUrl: freshlineOrderUrl,
                filesUploaded: files.length,
                files,
                timestamp: new Date().toISOString(),
                ...(uploadVerified ? {} : {
                    reason: 'Upload button clicked but file not found in attachments list after re-render',
                    missingFiles: missing,
                }),
            };

            await Actor.pushData(result);
            log.info('Results saved to dataset', result);

        } catch (error) {
            log.error(`Actor failed: ${error.message}`);

            // Take screenshot on failure
            try {
                const screenshot = await page.screenshot({ fullPage: true });
                await Actor.setValue('error-screenshot', screenshot, { contentType: 'image/png' });
                log.info('Error screenshot saved to key-value store as "error-screenshot"');
            } catch (screenshotError) {
                log.error(`Failed to capture screenshot: ${screenshotError.message}`);
            }

            // Save error details to dataset
            await Actor.pushData({
                success: false,
                error: error.message,
                orderUrl: freshlineOrderUrl,
                files,
                timestamp: new Date().toISOString(),
            });

            throw error;
        } finally {
            // Clean up downloaded temp files
            for (const filepath of downloadedPaths) {
                try {
                    await unlink(filepath);
                } catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
    },

    async failedRequestHandler({ request, log }, error) {
        log.error('Request failed', { url: request.url, error: error.message });
    },
});

// Run the crawler with a single request
await crawler.run([{ url: freshlineOrderUrl }]);

await Actor.exit();
