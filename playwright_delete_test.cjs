const { chromium } = require('playwright')
const fs = require('fs')

const TOKEN = fs.readFileSync('D:/workspace/ai-agent/kh_token.txt', 'utf8').trim()
const LOGIN = JSON.parse(fs.readFileSync('D:/workspace/ai-agent/kh_login.json', 'utf8'))
const USER = LOGIN.user

const AUTH_STATE = JSON.stringify({
  state: { token: TOKEN, user: USER, isAuthenticated: true },
  version: 0,
})

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()

  const consoleMsgs = []
  const pageErrors = []
  page.on('console', (m) => consoleMsgs.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  // 1) 先访问以建立 origin，再注入 localStorage，刷新
  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'domcontentloaded' })

  // 2) 等待任务列表渲染
  let delBtn = null
  try {
    await page.waitForSelector('.task-list .task-del-btn', { timeout: 20000 })
    delBtn = page.locator('.task-list').filter({ hasText: '任务 31' }).locator('.task-del-btn').first()
    const count = await page.locator('.task-list .task-del-btn').count()
    console.log('DELETE_BTN_COUNT=', count)
  } catch (e) {
    console.log('WAIT_TASK_LIST_FAILED:', e.message)
  }

  // 3) 截图（点击前）
  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/before_click.png', fullPage: true })

  // 4) 点击删除按钮
  let clickResult = 'NOT_CLICKED'
  if (delBtn) {
    try {
      await delBtn.click({ timeout: 5000 })
      clickResult = 'CLICKED'
    } catch (e) {
      clickResult = 'CLICK_FAILED: ' + e.message
    }
  }
  console.log('CLICK_RESULT=', clickResult)

  // 5) 等待并检测 antd Modal 是否出现
  let modalAppeared = false
  try {
    await page.waitForSelector('.ant-modal-confirm, .ant-modal-wrap, .ant-modal', { timeout: 4000 })
    modalAppeared = true
  } catch (e) {
    modalAppeared = false
  }
  console.log('MODAL_APPEARED=', modalAppeared)

  // 6) 检测是否有 message 警告（进行中提示）
  const warningText = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('.ant-message-notice, .ant-message'))
    return els.map((e) => e.innerText).join(' | ')
  })
  console.log('MESSAGE_TEXT=', JSON.stringify(warningText))

  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/after_click.png', fullPage: true })

  console.log('=== CONSOLE (last 30) ===')
  console.log(consoleMsgs.slice(-30).join('\n'))
  console.log('=== PAGE ERRORS ===')
  console.log(pageErrors.join('\n') || '(none)')

  await browser.close()
  console.log('TEST_DONE')
})().catch((e) => {
  console.error('SCRIPT_ERROR:', e)
  process.exit(1)
})
