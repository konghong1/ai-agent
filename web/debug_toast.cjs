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
    body: JSON.stringify({ message: '我习惯在代码块里用注释说明每一步。' }),
  });
  console.log('chat sent, waiting 22s...');
  await page.waitForTimeout(22000);

  await page.goto(`${UI}/memory`, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=长期记忆', { timeout: 10000 });
  await page.getByRole('tab', { name: /待确认候选/ }).click();
  await page.waitForTimeout(1000);

  const pendingTable = page.locator('table', { has: page.locator('thead th', { hasText: '候选内容' }) });
  await pendingTable.locator('tbody tr').first().locator('button').first().click({ timeout: 8000 });
  await page.waitForTimeout(800);

  // 诊断 message holder
  const diag = await page.evaluate(() => {
    const holders = Array.from(document.querySelectorAll('.ant-message'));
    const out = holders.map(h => {
      const cs = getComputedStyle(h);
      const rect = h.getBoundingClientRect();
      // 向上找 transform/filter/will-change/contain 祖先
      let p = h.parentElement;
      const ancestors = [];
      while (p && p !== document.body) {
        const s = getComputedStyle(p);
        const interesting = [];
        if (s.transform && s.transform !== 'none') interesting.push('transform=' + s.transform);
        if (s.filter && s.filter !== 'none') interesting.push('filter=' + s.filter);
        if (s.willChange && s.willChange !== 'auto') interesting.push('willChange=' + s.willChange);
        if (s.contain && s.contain !== 'none') interesting.push('contain=' + s.contain);
        if (s.position === 'relative' || s.position === 'absolute' || s.position === 'fixed') interesting.push('position=' + s.position);
        if (interesting.length) ancestors.push(p.tagName + '.' + (p.className && p.className.toString().slice(0, 40)) + ' :: ' + interesting.join(';'));
        p = p.parentElement;
      }
      const notice = h.querySelector('.ant-message-notice');
      return {
        holderClass: h.className && h.className.toString(),
        holderTop: cs.top,
        holderPosition: cs.position,
        holderRectTop: Math.round(rect.top),
        noticeRectTop: notice ? Math.round(notice.getBoundingClientRect().top) : null,
        transformedAncestors: ancestors.slice(0, 6),
      };
    });
    return { count: holders.length, holders: out, bodyTransform: getComputedStyle(document.body).transform, rootHtml: document.getElementById('root') ? document.getElementById('root').outerHTML.slice(0, 120) : 'NO ROOT' };
  });
  console.log('DIAG:', JSON.stringify(diag, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
