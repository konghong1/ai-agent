const { chromium } = require('playwright');

const BASE = 'http://localhost';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzg0MjY0NjkzfQ.o5R9BOb7rQrKHAQxfajJno-fsraF4PEq_wuTOrpmo-I';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push({ type: 'pageerror', text: e.message }));
  page.on('console', msg => { if (msg.type() === 'error') errors.push({ type: 'console', text: msg.text() }); });

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((token) => {
    localStorage.setItem('agent-auth', JSON.stringify({ state: { token, user: { id: 2, name: 'konghong' }, isAuthenticated: true }, version: 0 }));
  }, TOKEN);

  await page.goto(`${BASE}/ecommerce-gallery`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.task-cell', { timeout: 20000 });
  await page.waitForTimeout(1500);

  // Pick the FIRST completed cell that is NOT already busy/failed (a stable target).
  const target = await page.evaluate(() => {
    const cells = Array.from(document.querySelectorAll('.task-cell[data-record-id]'));
    for (const c of cells) {
      const hasImg = c.querySelector('.cell-media img');
      const alreadyBusy = c.classList.contains('is-busy');
      const alreadyFailed = c.classList.contains('is-failed');
      const rid = c.getAttribute('data-record-id');
      if (hasImg && !alreadyBusy && !alreadyFailed && rid) {
        const cap = c.querySelector('.cell-caption');
        return { rid, title: cap ? cap.textContent.trim() : '' };
      }
    }
    return null;
  });
  console.log('TARGET:', target ? `rec#${target.rid} "${target.title}"` : 'NONE');
  if (!target) { console.log('E2E_DONE: SKIP (no completed, non-busy cell)'); await browser.close(); return; }

  // Click its 重作 button
  const clicked = await page.evaluate((rid) => {
    const c = document.querySelector(`.task-cell[data-record-id="${rid}"]`);
    const btn = c && c.querySelector('.cell-redo-btn');
    if (btn) { btn.click(); return true; }
    return false;
  }, target.rid);
  console.log('REDO_BTN_CLICKED:', clicked);

  // Modal appears; ensure prompt filled; click 重新生成
  await page.waitForSelector('.redo-modal', { timeout: 8000 });
  const ta = await page.$('#redo-prompt');
  if (ta) { const v = await ta.inputValue(); if (!v.trim()) await ta.fill('重新生成一张高质量产品图'); }
  await page.click('.redo-modal .ant-btn-primary');
  console.log('SUBMITTED 重新生成');

  // Immediately check the SAME record id: should now show 生成中 (progress), not 生成失败
  await page.waitForTimeout(1200);
  const res = await page.evaluate((rid) => {
    const c = document.querySelector(`.task-cell[data-record-id="${rid}"]`);
    if (!c) return { found: false };
    const busy = !!c.querySelector('.cell-busy');
    const ft = c.querySelector('.cell-failed-text');
    const failed = !!ft;
    const failedText = ft ? ft.textContent : '';
    const busyText = c.querySelector('.cell-busy-text');
    return { found: true, busy, busyText: busyText ? busyText.textContent : '', failed, failedText };
  }, target.rid);
  console.log('AFTER_SUBMIT:', JSON.stringify(res));

  const progressShown = res.found && res.busy && !res.failed;
  console.log('PROGRESS_SHOWN:', progressShown);

  await page.screenshot({ path: 'verify-shots/redo_e2e.png', fullPage: false });
  console.log('PAGE_ERRORS:', errors.length ? errors : 'none');
  console.log('E2E_DONE:', progressShown && errors.length === 0 ? 'PASS ✅' : 'FAIL ❌');
  await browser.close();
})();
