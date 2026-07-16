const { chromium } = require('playwright')

const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzg0MjY0NjkzfQ.o5R9BOb7rQrKHAQxfajJno-fsraF4PEq_wuTOrpmo-I'

;(async () => {
  let user = { id: 2 }
  try {
    const r = await fetch('http://localhost/api/users/me', { headers: { Authorization: `Bearer ${TOKEN}` } })
    if (r.ok) user = await r.json()
  } catch (e) {}
  const AUTH_STATE = JSON.stringify({ state: { token: TOKEN, user, isAuthenticated: true }, version: 0 })

  const browser = await chromium.launch()
  const page = await browser.newPage()
  const consoleMsgs = []
  const pageErrors = []
  page.on('console', (m) => consoleMsgs.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/agents/chat', { waitUntil: 'domcontentloaded' })

  // 等会话列表渲染
  await page.waitForSelector('[data-thread-id]', { timeout: 20000 })
  await page.waitForTimeout(1200)

  const readOrder = () => page.$$eval('[data-thread-id]', (els) => els.map((e) => e.getAttribute('data-thread-id')))
  const before = await readOrder()
  console.log('WEB_LOADED = true')
  console.log('新建前 会话数 =', before.length, '| 顺序(前->后):', before)

  // 点“新建会话”
  await page.getByText('新建会话', { exact: true }).click()
  // 等待新会话项出现（数量增加 或 顶部出现新 id）
  await page.waitForFunction(
    (b) => {
      const ids = Array.from(document.querySelectorAll('[data-thread-id]')).map((e) => e.getAttribute('data-thread-id'))
      return ids.length > b.length || (ids.length === b.length && ids[0] && !b.includes(ids[0]))
    },
    before,
    { timeout: 15000 }
  )
  await page.waitForTimeout(600)

  const after = await readOrder()
  const topId = after[0]
  const isNew = !before.includes(topId)
  console.log('新建后 会话数 =', after.length, '| 顺序(前->后):', after)
  console.log('顶部会话 id =', topId, '| 是否为本次新建(不在旧列表中)?', isNew)

  // 后端交叉验证：GET /api/threads 第0位应 == 顶部 id
  let apiTop = null
  try {
    const r = await fetch('http://localhost/api/threads', { headers: { Authorization: `Bearer ${TOKEN}` } })
    if (r.ok) {
      const list = await r.json()
      apiTop = list[0] && list[0].id
    }
  } catch (e) {}
  console.log('后端 GET /api/threads 第0位 id =', apiTop, '| 与前端顶部一致?', apiTop === topId)

  const pass = isNew && after[0] === topId && apiTop === topId
  console.log('RESULT =', pass ? 'PASS ✅ 新建会话稳居列表最顶部(创建时间倒序)' : 'FAIL ❌')

  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/chat_order_e2e.png', fullPage: false })
  console.log('\n=== CONSOLE (last 12) ===')
  console.log(consoleMsgs.slice(-12).join('\n'))
  console.log('=== PAGE ERRORS ===')
  console.log(pageErrors.join('\n') || '(none)')

  await browser.close()
  console.log('E2E_DONE')
  process.exit(pass ? 0 : 1)
})().catch((e) => {
  console.error('SCRIPT_ERROR:', e)
  process.exit(1)
})
