const { chromium } = require('playwright');
const API = 'http://127.0.0.1:8010';
const UI = 'http://127.0.0.1:5173';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const log = (...a) => console.log(...a);

  // 1) admin login (real account that owns the pending candidates)
  const r = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' }),
  });
  const data = await r.json();
  const token = data.access_token;
  const user = data.user;
  log('[ok] admin login, token len', token.length);

  // inject auth so the SPA thinks we are logged in
  await page.addInitScript((v) => {
    localStorage.setItem('agent-auth', v);
  }, JSON.stringify({ state: { token, user, isAuthenticated: true }, version: 0 }));

  // 2) open the memory panel
  await page.goto(`${UI}/memory`, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=长期记忆', { timeout: 10000 });
  log('[ok] 面板已打开，默认 Tab = 显式记忆(可能空)');

  // 3) switch to 待确认候选 Tab
  await page.getByRole('tab', { name: /待确认候选/ }).click();
  await page.waitForTimeout(800);

  // 4) assert the candidate appears
  const hasXiaohuasheng = await page.getByText('你好，小花生').isVisible().catch(() => false);
  const hasZhongwen = await page.getByText('简体中文').isVisible().catch(() => false);
  await page.screenshot({ path: '/c/workspace/ai-agent/verify-shots/admin_pending_tab.png', fullPage: true });
  log('[候选可见] 你好小花生 =', hasXiaohuasheng, '| 简体中文 =', hasZhongwen);
  log(hasXiaohuasheng && hasZhongwen ? 'RESULT: 候选 Tab 正确渲染候选 ✅' : 'RESULT: 候选未渲染 ❌');

  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(3); });
