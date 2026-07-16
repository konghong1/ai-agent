const { chromium } = require('playwright');
const fs = require('fs');

const BASE = 'http://localhost';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzg0MjY0NjkzfQ.o5R9BOb7rQrKHAQxfajJno-fsraF4PEq_wuTOrpmo-I';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push({ type: 'pageerror', text: e.message }));
  page.on('console', msg => { if (msg.type() === 'error') errors.push({ type: 'console', text: msg.text() }); });

  // Inject login token
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((token) => {
    localStorage.setItem('agent-auth', JSON.stringify({ state: { token, user: { id: 2, name: 'konghong' }, isAuthenticated: true }, version: 0 }));
  }, TOKEN);

  await page.goto(`${BASE}/agents/chat`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-thread-id]', { timeout: 15000 });

  // Capture initial order
  const initialIds = await page.$$eval('[data-thread-id]', els => els.map(el => el.getAttribute('data-thread-id')));
  console.log('WEB_LOADED initial order:', initialIds);

  // Click new conversation button
  await page.locator('button', { hasText: '新建会话' }).click();
  await page.waitForTimeout(2000);

  // Capture new order
  const afterIds = await page.$$eval('[data-thread-id]', els => els.map(el => el.getAttribute('data-thread-id')));
  console.log('AFTER_CREATE order:', afterIds);

  const newOne = afterIds.find(id => !initialIds.includes(id));
  console.log('NEW_THREAD_ID:', newOne);
  const isNewAtBottom = newOne === afterIds[afterIds.length - 1];
  console.log('NEW_AT_BOTTOM:', isNewAtBottom, '(期望 true: 新建会话在最下面)');

  const messages = await page.$$eval('.chat-messages .message, [class*="message"]', els => els.length);
  console.log('MESSAGE_COUNT:', messages);

  await page.screenshot({ path: 'verify-shots/chat_ascending_e2e.png', fullPage: false });
  console.log('PAGE_ERRORS:', errors.length ? errors : 'none');
  console.log('E2E_DONE:', isNewAtBottom && errors.length === 0 ? 'PASS ✅' : 'FAIL ❌');
  await browser.close();
})();
