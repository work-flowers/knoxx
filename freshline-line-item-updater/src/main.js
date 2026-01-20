import 'dotenv/config';
import { Actor } from 'apify';
import { PuppeteerCrawler, log } from 'crawlee';

await Actor.init();

// Get input from Apify (from Zapier webhook or manual run)
const input = await Actor.getInput();

// Validate input
if (!input?.freshlineOrderUrl || !input?.lineItems) {
    throw new Error('Invalid input: freshlineOrderUrl and lineItems are required');
}

const { freshlineOrderUrl, lineItems } = input;

// Get credentials from environment variables
const username = process.env.FRESHLINE_USERNAME;
const password = process.env.FRESHLINE_PASSWORD;

if (!username || !password) {
    throw new Error('Missing credentials: FRESHLINE_USERNAME and FRESHLINE_PASSWORD environment variables must be set');
}

log.info('Starting Freshline Line Item Updater', {
    orderUrl: freshlineOrderUrl,
    lineItemCount: lineItems.length,
});

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

            // Wait for login form
            await page.waitForSelector('#staff_email', { timeout: 10000 });
            log.info('Login page loaded');

            // Fill in credentials
            await page.type('#staff_email', username);
            await page.type('#staff_password', password);
            log.info('Credentials entered');

            // Submit the form by pressing Enter on the password field
            // This is more reliable than clicking the submit button
            await page.focus('#staff_password');
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
                page.keyboard.press('Enter'),
            ]);

            log.info('Form submitted');

            // Wait a moment for any redirects to complete
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Check for login errors
            const loginError = await page.$('.error-message, .alert-error');
            if (loginError) {
                const errorText = await page.evaluate(el => el.textContent, loginError);
                throw new Error(`Login failed: ${errorText}`);
            }

            // Verify we're not still on the login page
            const currentUrl = page.url();
            if (currentUrl.includes('/login')) {
                throw new Error('Still on login page after attempting login. Check credentials.');
            }

            log.info('Login successful', { currentUrl });

            // Step 2: Navigate to the order edit page
            log.info(`Navigating to order: ${freshlineOrderUrl}`);
            await page.goto(freshlineOrderUrl, {
                waitUntil: 'domcontentloaded',
                timeout: 60000,
            });

            // Wait for Phoenix LiveView to load and render line items
            // Phoenix LiveView apps need extra time to initialize
            await new Promise(resolve => setTimeout(resolve, 3000)); // Give Phoenix time to connect

            // Wait for line items to load with longer timeout
            try {
                await page.waitForSelector('#line-items', { timeout: 20000 });
                log.info('Order page loaded');
            } catch (error) {
                // If line items don't appear, take a screenshot and log the page HTML
                log.error('Failed to find #line-items. Taking debug screenshot...');
                const html = await page.content();
                log.info('Page HTML length:', html.length);
                throw new Error('Line items container not found on page. Check error screenshot for details.');
            }

            // Step 3: Get all line item containers
            const lineItemElements = await page.$$('#line-items > li');
            log.info(`Found ${lineItemElements.length} line items on page`);

            let updatedCount = 0;
            const notFoundSkus = [];
            const updateDetails = [];

            // Step 4: Process each input line item
            for (const inputItem of lineItems) {
                const { sku, lot, expiry } = inputItem;
                log.info(`Processing input SKU: ${sku}`);

                let found = false;

                // Search through all line items on the page
                for (const liElement of lineItemElements) {
                    // Get the SKU from the span.font-mono element
                    const skuElement = await liElement.$('span.font-mono');
                    if (!skuElement) {
                        continue;
                    }

                    const pageSku = await page.evaluate(el => el.textContent.trim(), skuElement);

                    // Check if this matches our input SKU
                    if (pageSku === sku) {
                        found = true;
                        log.info(`Matched SKU: ${sku}`);

                        // Get the parent <li> id to construct the textarea selector
                        const liId = await page.evaluate(el => el.id, liElement);
                        const textareaSelector = `#${liId}_vendor_notes`;

                        // Build the notes text
                        const notesText = `Lot: ${lot}, BBD: ${expiry}`;

                        // Clear existing content and enter new notes
                        await page.evaluate((selector, text) => {
                            const textarea = document.querySelector(selector);
                            if (textarea) {
                                textarea.value = text;
                                // Trigger change event for any listeners
                                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }, textareaSelector, notesText);

                        log.info(`Updated ${sku} with: ${notesText}`);
                        updatedCount++;
                        updateDetails.push({ sku, lot, expiry, success: true });
                        break;
                    }
                }

                if (!found) {
                    notFoundSkus.push(sku);
                    log.warning(`SKU not found on page: ${sku}`);
                    updateDetails.push({ sku, lot, expiry, success: false, reason: 'SKU not found on page' });
                }
            }

            // Step 5: Save the order if any updates were made
            if (updatedCount > 0) {
                log.info(`Saving order with ${updatedCount} updated line items...`);

                // Find and click the Save button by searching all buttons for "Save" text
                const buttons = await page.$$('button');
                let saveButton = null;

                for (const button of buttons) {
                    const buttonText = await page.evaluate(el => el.textContent.trim(), button);
                    if (buttonText === 'Save') {
                        saveButton = button;
                        break;
                    }
                }

                if (!saveButton) {
                    throw new Error('Could not find Save button');
                }

                await saveButton.click();
                log.info('Save button clicked');

                // Wait for save operation (Phoenix LiveView will update the page)
                // Give it a few seconds for the save to complete
                await new Promise(resolve => setTimeout(resolve, 3000));

                // Check for any error messages after save
                const saveError = await page.$('.error-message, .alert-error');
                if (saveError) {
                    const errorText = await page.evaluate(el => el.textContent, saveError);
                    throw new Error(`Save failed: ${errorText}`);
                }

                log.info('Order saved successfully');
            } else {
                log.warning('No line items were updated, skipping save');
            }

            // Store results in Apify dataset
            const result = {
                success: updatedCount > 0,
                orderUrl: freshlineOrderUrl,
                lineItemsProcessed: lineItems.length,
                lineItemsUpdated: updatedCount,
                notFoundSkus,
                updateDetails,
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
                orderUrl: freshlineOrderUrl,
                timestamp: new Date().toISOString(),
            });

            throw error;
        }
    },

    async failedRequestHandler({ request, log }, error) {
        log.error('Request failed', { url: request.url, error: error.message });
    },
});

// Run the crawler with a single request
await crawler.run([{ url: freshlineOrderUrl }]);

await Actor.exit();
