import 'dotenv/config';
import { Actor } from 'apify';
import { PuppeteerCrawler, log } from 'crawlee';

await Actor.init();

// Get input from Apify (from Zapier webhook or manual run)
const input = await Actor.getInput();

// Validate input
if (!input?.freshlineOrderUrl || !input?.salesOrderId || !input?.salesOrderUuid) {
    throw new Error('Invalid input: freshlineOrderUrl, salesOrderId, and salesOrderUuid are required');
}

const { salesOrderId, salesOrderUuid } = input;

// Ensure we use the order view URL (not edit) — custom data is on the view page
const freshlineOrderUrl = input.freshlineOrderUrl.replace(/\/edit\/?$/, '');

// Get credentials from environment variables
const username = process.env.FRESHLINE_USERNAME;
const password = process.env.FRESHLINE_PASSWORD;

if (!username || !password) {
    throw new Error('Missing credentials: FRESHLINE_USERNAME and FRESHLINE_PASSWORD environment variables must be set');
}

// Build the custom data payload
const customDataPayload = {
    sales_order: {
        id: salesOrderId,
        uuid: salesOrderUuid,
    },
};
const customDataJson = JSON.stringify(customDataPayload, null, 2);

log.info('Starting Freshline Order Data Updater', {
    orderUrl: freshlineOrderUrl,
    salesOrderId,
    salesOrderUuid,
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

            // Step 2: Navigate to the order view page (custom data is on view, not edit)
            log.info(`Navigating to order: ${freshlineOrderUrl}`);
            await page.goto(freshlineOrderUrl, {
                waitUntil: 'domcontentloaded',
                timeout: 60000,
            });

            // Phoenix LiveView initialization delay
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Scroll down to ensure the custom data section loads
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Wait for the custom data table to appear
            try {
                await page.waitForSelector('#order-custom-data-definitions', { timeout: 15000 });
                log.info('Order page loaded, custom data section found');
            } catch (error) {
                log.error('Failed to find custom data section. Taking debug screenshot...');
                throw new Error('Custom data table not found on page. Check error screenshot for details.');
            }

            // Find and click the edit button for the "Carton Cloud Sales Order" row
            const editButtonClicked = await page.evaluate(() => {
                const tbody = document.querySelector('#order-custom-data-definitions');
                if (!tbody) return { found: false, error: 'Custom data table not found' };

                const rows = tbody.querySelectorAll('tr');
                for (const row of rows) {
                    const label = row.querySelector('[alt="custom.carton-cloud-sales-order-id"]');
                    if (label) {
                        const button = row.querySelector('button');
                        if (button) {
                            button.click();
                            return { found: true };
                        }
                        return { found: false, error: 'Edit button not found in Carton Cloud Sales Order row' };
                    }
                }
                return { found: false, error: 'Carton Cloud Sales Order row not found in custom data table' };
            });

            if (!editButtonClicked.found) {
                throw new Error(editButtonClicked.error);
            }

            log.info('Edit button clicked for Carton Cloud Sales Order');

            // Wait for the modal to appear
            await page.waitForSelector('#schema_value_json', { timeout: 10000 });
            log.info('Edit modal opened');

            // Step 4: Clear the textarea and enter the JSON payload
            await page.evaluate((value) => {
                const textarea = document.querySelector('#schema_value_json');
                textarea.value = value;
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
            }, customDataJson);

            log.info('Custom data field updated', {
                salesOrderId,
                salesOrderUuid,
                jsonLength: customDataJson.length,
            });

            // Step 5: Click the Save button inside the modal
            // The modal has its own Save button (distinct from the main order Save)
            const modalSaved = await page.evaluate(() => {
                // Find the Save button within the modal context
                // The modal Save button is near the Delete link and "Go to definition" link
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim();
                    if (text === 'Save') {
                        button.click();
                        return true;
                    }
                }
                return false;
            });

            if (!modalSaved) {
                throw new Error('Could not find Save button in the custom data modal');
            }

            log.info('Modal Save button clicked');

            // Wait for save operation (Phoenix LiveView will process the update)
            await new Promise(resolve => setTimeout(resolve, 3000));

            log.info('Custom data saved successfully');

            // Step 5: Store results
            const result = {
                success: true,
                orderUrl: freshlineOrderUrl,
                salesOrderId,
                salesOrderUuid,
                customDataJson: customDataPayload,
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
                salesOrderId,
                salesOrderUuid,
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
