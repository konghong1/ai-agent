const { chromium } = require('playwright');
const API = 'http://127.0.0.1:8010';
const UI = 'http://127.0.0.1:80';
const SEEDED_ID = parseInt(process.argv[2], 10);
const j = (u, o) => fetch(u, o).then(r => r.json());

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const data = await j(`${API}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' }) });
  const tok = data.access_token;
  const H = { Authorization: `Bearer ${tok}` };
  await page.addInitScript((v) => localStorage.setItem('agent-auth', v),
    JSON.stringify({ state: { token: tok, user: data.user, isAuthenticated: true }, version: 0 }));

  await page.goto(`${UI}/memory`, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=长期记忆', { timeout: 10000 });
  await page.getByRole('tab', { name: /待确认候选/ }).click();
  await page.waitForSelector(`[data-testid="accept-${SEEDED_ID}"]`, { timeout: 12000 });

  await page.locator(`[data-testid="accept-${SEEDED_ID}"]`).click({ timeout: 8000 });

  // 点击后每 100ms 记录 toast top，持续 5s（toast 在 accept API + load 之后才出现，需足够窗口）
  const samples = [];
  for (let i = 0; i < 50; i++) {
    await page.waitForTimeout(100);
    const s = await page.evaluate(() => {
      const ns = document.querySelectorAll('.ant-message-notice');
      if (!ns.length) return null;
      const r = ns[ns.length - 1].getBoundingClientRect();
      return { top: Math.round(r.top), text: (ns[ns.length - 1].innerText || '').trim() };
    });
    if (s) { samples.push(s); if (i === 30 || i === 48) await page.screenshot({ path: `verify-shots/accept_toast_${i}.png` }); }
  }
  const tops = samples.map(s => s.top);
  const settled = samples.slice(-5).map(s => s.top); // 末段（动画后应稳定）
  const everVisible = tops.some(t => t >= 0 && t < 300);
  const last = samples[samples.length - 1];
  console.log('[SAMPLES] tops=', JSON.stringify(tops));
  console.log('[SETTLED] last5 tops=', JSON.stringify(settled), '| last=', JSON.stringify(last));
  console.log('[VERDICT] everVisible(in viewport):', everVisible, '| final top:', last ? last.top : 'none', '| text:', last ? last.text : '');
  await browser.close();
  process.exit(everVisible ? 0 : 1);
})().catch(e => { console.error('[FATAL]', e); process.exit(3); });
