import 'dotenv/config';
import { Actor } from 'apify';
import { PuppeteerCrawler, log } from 'crawlee';
import { writeFile, unlink } from 'node:fs/promises';
import { basename } from 'node:path';

await Actor.init();

// Get input from Apify (from Zapier webhook or manual run)
const input = await Actor.getInput();

// Validate input
if (!input?.cartonCloudDocumentUrl || !input?.files) {
    throw new Error('Invalid input: cartonCloudDocumentUrl and files are required');
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

const cartonCloudDocumentUrl = input.cartonCloudDocumentUrl;
const documentName = input.documentName || 'Packing Confirmation';
const description = input.description || '';

// Get credentials from environment variables
const username = process.env.CARTONCLOUD_USERNAME;
const password = process.env.CARTONCLOUD_PASSWORD;

if (!username || !password) {
    throw new Error('Missing credentials: CARTONCLOUD_USERNAME and CARTONCLOUD_PASSWORD environment variables must be set');
}

log.info('Starting CartonCloud Order Attachment', {
    documentUrl: cartonCloudDocumentUrl,
    fileCount: files.length,
    documentName,
});

// Download a file from URL to /tmp/ with optional custom name
async function downloadFile(url, customName) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
    }

    const buffer = Buffer.from(await response.arrayBuffer());

    // Use custom name if provided, otherwise derive from URL
    let filename = customName || decodeURIComponent(basename(new URL(url).pathname)) || 'attachment';

    const filepath = `/tmp/${filename}`;
    await writeFile(filepath, buffer);
    log.info(`Downloaded: ${filename} (${buffer.length} bytes)`);
    return filepath;
}

// Download all files before starting the browser
log.info('Downloading files...');
const downloadedPaths = [];
for (const { url, name } of files) {
    const path = await downloadFile(url, name);
    downloadedPaths.push(path);
}
log.info(`All ${downloadedPaths.length} files downloaded`);

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
            // Step 1: Navigate to the Add Document page (will redirect to login if not authenticated)
            log.info(`Navigating to: ${cartonCloudDocumentUrl}`);
            await page.goto(cartonCloudDocumentUrl, {
                waitUntil: 'networkidle2',
                timeout: 30000,
            });

            // Step 2: Handle login if redirected
            const loginInput = await page.$('input[name="email"]');
            if (loginInput) {
                log.info('Login page detected, entering credentials...');

                await page.type('input[name="email"]', username);
                await page.type('input[name="password"]', password);
                log.info('Credentials entered');

                // Wait for the Sign in button to become enabled
                await page.waitForFunction(() => {
                    const btn = document.querySelector('button[type="submit"]');
                    return btn && !btn.disabled;
                }, { timeout: 5000 });

                // Click Sign in and wait for navigation
                await Promise.all([
                    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
                    page.click('button[type="submit"]'),
                ]);

                log.info('Login submitted');

                // Wait for any redirects to complete
                await new Promise(resolve => setTimeout(resolve, 2000));

                // Check if still on login page
                const stillOnLogin = await page.$('input[name="email"]');
                if (stillOnLogin) {
                    throw new Error('Login failed. Check CARTONCLOUD_USERNAME and CARTONCLOUD_PASSWORD.');
                }

                log.info('Login successful', { currentUrl: page.url() });

                // If not redirected back to the document URL, navigate there
                if (!page.url().includes('/documents/add')) {
                    log.info('Navigating to Add Document page...');
                    await page.goto(cartonCloudDocumentUrl, {
                        waitUntil: 'networkidle2',
                        timeout: 30000,
                    });
                }
            }

            // Wait for the Add Document form to load
            await page.waitForSelector('[data-testid="save-button"]', { timeout: 15000 });
            log.info('Add Document form loaded');

            // Step 3: Set the Name dropdown
            log.info(`Setting document name to: ${documentName}`);
            // The Name field is a React custom dropdown — click to open, then select the option
            const nameSet = await page.evaluate((targetName) => {
                // Find the label "Name" and its associated dropdown
                const labels = document.querySelectorAll('label, div');
                for (const label of labels) {
                    if (label.textContent.trim() === 'Name' && label.nextElementSibling) {
                        // The dropdown trigger should be nearby
                        break;
                    }
                }

                // Look for the currently displayed value in the dropdown
                // CartonCloud uses a custom select component — find and click it
                const dropdownButtons = document.querySelectorAll('[role="combobox"], [role="listbox"], select');
                for (const el of dropdownButtons) {
                    if (el.tagName === 'SELECT') {
                        // It's a native select — set value directly
                        const options = el.querySelectorAll('option');
                        for (const opt of options) {
                            if (opt.textContent.trim() === targetName) {
                                el.value = opt.value;
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                return 'native-select';
                            }
                        }
                    }
                }

                return null;
            }, documentName);

            if (nameSet === 'native-select') {
                log.info('Document name set via native select');
            } else {
                // Try clicking the dropdown to open it and select the option
                // Find the dropdown near the "Name" heading
                const clicked = await page.evaluate((targetName) => {
                    // Find elements that look like a dropdown showing a value
                    const allButtons = document.querySelectorAll('button, [role="button"], [class*="select"]');
                    for (const btn of allButtons) {
                        const text = btn.textContent.trim();
                        if (text === 'Packing Confirmation' || text === 'Other') {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }, documentName);

                if (clicked) {
                    // Wait for dropdown menu to appear
                    await new Promise(resolve => setTimeout(resolve, 500));

                    // Click the target option
                    const optionClicked = await page.evaluate((targetName) => {
                        const options = document.querySelectorAll('[role="option"], li, [class*="option"]');
                        for (const opt of options) {
                            if (opt.textContent.trim() === targetName) {
                                opt.click();
                                return true;
                            }
                        }
                        return false;
                    }, documentName);

                    if (optionClicked) {
                        log.info('Document name selected from dropdown');
                    } else {
                        log.warning(`Could not find option "${documentName}" in dropdown — it may already be selected`);
                    }
                } else {
                    log.warning('Could not find Name dropdown trigger — default value may already be correct');
                }
            }

            // Step 4: Fill Description (if provided)
            if (description) {
                log.info('Entering description...');
                await page.type('textarea[name="description"]', description);
                log.info('Description entered');
            }

            // Step 5: Upload files
            log.info('Uploading files...');
            const fileInput = await page.$('input[data-testid="file-input"]');
            if (!fileInput) {
                throw new Error('File input (input[data-testid="file-input"]) not found on page');
            }

            // Standard HTML file input — uploadFile() works at CDP level even on hidden inputs
            await fileInput.uploadFile(...downloadedPaths);
            log.info('Files set on input element');

            // Wait for the UI to process the files
            await new Promise(resolve => setTimeout(resolve, 5000));

            // Step 6: Click Save
            log.info('Clicking Save button...');
            await page.click('[data-testid="save-button"]');

            // Wait for save to complete
            await new Promise(resolve => setTimeout(resolve, 5000));

            log.info('Document saved successfully');

            // Step 7: Store results
            const result = {
                success: true,
                documentUrl: cartonCloudDocumentUrl,
                filesUploaded: files.length,
                files,
                documentName,
                description,
                timestamp: new Date().toISOString(),
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
                documentUrl: cartonCloudDocumentUrl,
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
await crawler.run([{ url: cartonCloudDocumentUrl }]);

await Actor.exit();
