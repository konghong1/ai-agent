const { chromium } = require('playwright');

const TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzg0MjY0NjkzfQ.o5R9BOb7rQrKHAQxfajJno-fsraF4PEq_wuTOrpmo-I";

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' });
  await page.evaluate((t) => localStorage.setItem('agent-auth', JSON.stringify({
    state: { token: t, user: { id: 2 }, isAuthenticated: true }, version: 0
  })), TOKEN);
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);

  // 从 API 取 task 38 / 39 的 record id 列表
  const api = await page.evaluate(async (t) => {
    const r = await fetch('http://localhost:8010/api/gallery/tasks', { headers: { Authorization: 'Bearer ' + t } });
    const data = await r.json();
    const out = {};
    for (const task of data) {
      if (task.id === 38 || task.id === 39) {
        out[task.id] = {
          status: task.status,
          done: task.done,
          total: task.total,
          recs: (task.records || []).map(x => ({ id: x.id, status: x.status })),
        };
      }
    }
    return out;
  }, TOKEN);

  // 在 DOM 中检查这些 record 的单元格是否仍处于“生成中”(is-busy)
  const dom = await page.evaluate((api) => {
    const res = {};
    for (const tid of [38, 39]) {
      const t = api[tid];
      if (!t) { res[tid] = 'task-missing-in-api'; continue; }
      let busy = 0, completed = 0, failed = 0;
      for (const rec of t.recs) {
        const cell = document.querySelector(`[data-record-id="${rec.id}"]`);
        if (!cell) continue;
        if (cell.classList.contains('is-busy')) busy++;
        else if (cell.classList.contains('is-failed')) failed++;
        else completed++;
      }
      res[tid] = { apiStatus: t.status, apiDone: `${t.done}/${t.total}`, domBusy: busy, domCompleted: completed, domFailed: failed };
    }
    return res;
  }, api);

  console.log('API_STATE=' + JSON.stringify(api));
  console.log('DOM_STATE=' + JSON.stringify(dom));

  await page.screenshot({ path: 'verify-shots/gallery_fix_e2e.png', fullPage: false });

  // 断言：task 38 应已 completed 且 DOM 中无 busy 单元格（不再“一直生成中”）
  const t38 = dom[38];
  const pass = t38 && t38.apiStatus === 'completed' && t38.domBusy === 0;
  console.log('TASK38_RECOVERED=' + (t38 ? t38.apiStatus : 'n/a'));
  console.log('TASK38_DOM_BUSY=' + (t38 ? t38.domBusy : 'n/a'));
  console.log('PAGE_ERRORS=' + errors.length);
  console.log('E2E_RESULT=' + (pass && errors.length === 0 ? 'PASS ✅ 卡死任务已修复，前端不再“一直生成中”' : 'CHECK ⚠️ 见上方状态'));

  await browser.close();
})().catch(e => { console.error('E2E_FATAL', e); process.exit(1); });
