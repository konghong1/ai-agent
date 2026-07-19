const { chromium } = require('playwright');
const API = 'http://127.0.0.1:8010';
const UI = 'http://127.0.0.1:5173';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const r = await fetch(`${API}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' }),
  });
  const data = await r.json();
  const tok = data.access_token;
  await page.addInitScript((v) => localStorage.setItem('agent-auth', v),
    JSON.stringify({ state: { token: tok, user: data.user, isAuthenticated: true }, version: 0 }));

  await fetch(`${API}/api/chat`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
    body: JSON.stringify({ message: '我习惯在代码块里用注释说明每一步。标记' + Date.now() }),
  });
  console.log('chat sent, waiting 22s...');
  await page.waitForTimeout(22000);

  await page.goto(`${UI}/memory`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('text=长期记忆', { timeout: 10000 });
  await page.getByRole('tab', { name: /待确认候选/ }).click();
  await page.waitForTimeout(1000);

  const pendingTable = page.locator('table', { has: page.locator('thead th', { hasText: '候选内容' }) });
  await pendingTable.locator('tbody tr').first().locator('button').first().click({ timeout: 8000 });
  console.log('clicked accept, polling toast for 3s...');

  for (let i = 0; i < 30; i++) {
    const snap = await page.evaluate(() => {
      const h = document.querySelector('.ant-message');
      const n = document.querySelector('.ant-message-notice');
      if (!n) return { has: false };
      const cs = getComputedStyle(n);
      const box = n.getBoundingClientRect();
      return {
        has: true,
        holderClass: h ? h.className.toString() : null,
        holderTop: h ? getComputedStyle(h).top : null,
        noticeTransform: cs.transform,
        noticeTransition: cs.transition,
        noticeAnimation: cs.animation,
        noticeOpacity: cs.opacity,
        y: Math.round(box.top),
        h: Math.round(box.height),
      };
    });
    console.log((i * 100) + 'ms', JSON.stringify(snap));
    await page.waitForTimeout(100);
  }
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
