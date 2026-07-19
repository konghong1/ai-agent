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

  await page.goto(`${UI}/memory`, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=长期记忆', { timeout: 10000 });

  // 安装 MutationObserver：一旦 .ant-message 出现，立即抓取其真实定位
  await page.evaluate(() => {
    window.__cap = [];
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        m.addedNodes.forEach((n) => {
          const el = n.nodeType === 1 ? n : null;
          const holder = el && (el.classList && el.classList.contains('ant-message')) ? el
            : (el && el.querySelector && el.querySelector('.ant-message'));
          if (holder) {
            const cs = getComputedStyle(holder);
            const box = holder.getBoundingClientRect();
            let p = holder.parentElement, anc = [];
            while (p && p !== document.body) {
              const s = getComputedStyle(p);
              const arr = [];
              if (s.transform && s.transform !== 'none') arr.push('transform=' + s.transform);
              if (s.filter && s.filter !== 'none') arr.push('filter=' + s.filter);
              if (s.contain && s.contain !== 'none') arr.push('contain=' + s.contain);
              if (s.position !== 'static') arr.push('position=' + s.position);
              if (arr.length) anc.push(p.tagName + '.' + (p.className && p.className.toString().slice(0,30)) + '::' + arr.join(';'));
              p = p.parentElement;
            }
            window.__cap.push({
              t: Date.now(),
              cls: holder.className.toString(),
              top: cs.top, position: cs.position, transform: cs.transform, zIndex: cs.zIndex,
              boxTop: Math.round(box.top), boxLeft: Math.round(box.left),
              ancestors: anc.slice(0, 5),
            });
          }
        });
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });
  });

  // 确定性触发 message：点「新建记忆」→ 填表 → 保存（submit 里调 message.success）
  await page.getByTestId('mem-new').click();
  await page.waitForTimeout(300);
  await page.locator('input[placeholder="如：语言偏好"]').fill('测试键' + Date.now());
  await page.locator('textarea[placeholder="如：用户偏好使用简体中文"]').fill('测试值');
  await page.getByTestId('mem-save').click();
  console.log('clicked save, waiting for message...');
  await page.waitForTimeout(2500);

  const caps = await page.evaluate(() => window.__cap);
  console.log('CAPS:', JSON.stringify(caps, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
