const { chromium } = require('playwright')

const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzg0MjY0NjkzfQ.o5R9BOb7rQrKHAQxfajJno-fsraF4PEq_wuTOrpmo-I'

;(async () => {
  // 拉真实 user（避免 user 字段缺失导致页面崩溃）
  let user = { id: 2 }
  try {
    const r = await fetch('http://localhost/api/users/me', { headers: { Authorization: `Bearer ${TOKEN}` } })
    if (r.ok) user = await r.json()
  } catch (e) {}
  console.log('USER =', JSON.stringify(user).slice(0, 120))

  const AUTH_STATE = JSON.stringify({ state: { token: TOKEN, user, isAuthenticated: true }, version: 0 })

  const browser = await chromium.launch()
  const page = await browser.newPage()
  const consoleMsgs = []
  const pageErrors = []
  page.on('console', (m) => consoleMsgs.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'domcontentloaded' })

  // 等待任务卡片渲染
  await page.waitForSelector('.task-list', { timeout: 20000 })
  await page.waitForTimeout(1500)

  // 抓取所有任务卡片的文本 + 是否含“卡死”警告
  const cards = await page.$$eval('.task-list > *', (els) =>
    els.map((el) => ({
      text: el.innerText || '',
      hasStuck: /任务疑似卡死/.test(el.innerText || ''),
      hasRunning: /创作中|后台生成中|生成中|进行中/.test(el.innerText || ''),
    }))
  )

  const TARGET = 38
  const targetCard = cards.find((c) => new RegExp('任务\\s*' + TARGET).test(c.text))
  console.log('WEB_LOADED = true')
  console.log('总卡片数 =', cards.length)
  console.log('显示“卡死”警告的卡片数 =', cards.filter((c) => c.hasStuck).length)
  cards.filter((c) => c.hasStuck).forEach((c) => {
    const m = c.text.match(/任务\s*\d+/)
    console.log('  ⚠ 卡死卡片:', m ? m[0] : '(未知)', '|', c.text.replace(/\s+/g, ' ').slice(0, 80))
  })

  if (targetCard) {
    console.log(`\n=== 目标任务 ${TARGET}（你刚点的那个） ===`)
    console.log('  含“卡死”警告 =', targetCard.hasStuck, '  (期望 false)')
    console.log('  含“进行中”   =', targetCard.hasRunning, '  (期望 true)')
    console.log('  卡片文本片段 =', targetCard.text.replace(/\s+/g, ' ').slice(0, 140))
    const pass = targetCard.hasStuck === false && targetCard.hasRunning === true
    console.log('TARGET_RESULT =', pass ? 'PASS ✅ 不再误报卡死' : 'FAIL ❌')
  } else {
    console.log(`未找到任务 ${TARGET} 的卡片（可能未渲染/被收起）`)
  }

  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/stuck_e2e.png', fullPage: true })
  console.log('\n=== CONSOLE (last 15) ===')
  console.log(consoleMsgs.slice(-15).join('\n'))
  console.log('=== PAGE ERRORS ===')
  console.log(pageErrors.join('\n') || '(none)')

  await browser.close()
  console.log('E2E_DONE')
})().catch((e) => {
  console.error('SCRIPT_ERROR:', e)
  process.exit(1)
})
