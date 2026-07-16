const { chromium } = require('playwright')
const fs = require('fs')

const TOKEN = fs.readFileSync('D:/workspace/ai-agent/kh_token.txt', 'utf8').trim()
const LOGIN = JSON.parse(fs.readFileSync('D:/workspace/ai-agent/kh_login.json', 'utf8'))
const USER = LOGIN.user

const AUTH_STATE = JSON.stringify({
  state: { token: TOKEN, user: USER, isAuthenticated: true },
  version: 0,
})

async function apiGetTasks() {
  const r = await fetch('http://localhost/api/gallery/tasks', {
    headers: { Authorization: `Bearer ${TOKEN}` },
  })
  const data = await r.json()
  return Array.isArray(data) ? data : (data.items || [])
}

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const consoleMsgs = []
  const pageErrors = []
  page.on('console', (m) => consoleMsgs.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'domcontentloaded' })

  await page.waitForSelector('.task-list .task-del-btn', { timeout: 20000 })

  // 删除前：确认任务 31 在列表中
  let tasksBefore = await apiGetTasks()
  console.log('BEFORE: task31 present =', tasksBefore.some((t) => t.id === 31))

  // 点任务 31 的删除按钮
  const delBtn = page.locator('.task-list').filter({ hasText: '任务 31' }).locator('.task-del-btn').first()
  await delBtn.click({ timeout: 5000 })
  console.log('CLICKED delete on 任务 31')

  // 等待确认弹框
  let modal = false
  try {
    await page.waitForSelector('.ant-modal-confirm', { timeout: 4000 })
    modal = true
  } catch (e) {}
  console.log('MODAL_APPEARED =', modal)

  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/modal_shown.png', fullPage: true })

  if (modal) {
    // 点击弹框里的「删除」按钮（danger 主按钮）
    const okBtn = page.locator('.ant-modal-confirm .ant-btn-dangerous').first()
    await okBtn.click({ timeout: 5000 })
    console.log('CLICKED OK (删除) in modal')
    // 等待删除请求 + 前端列表更新
    await page.waitForTimeout(2500)
  }

  // 删除后：确认任务 31 已不在列表
  let tasksAfter = await apiGetTasks()
  console.log('AFTER: task31 present =', tasksAfter.some((t) => t.id === 31))
  console.log('DELETE_SUCCESS =', !tasksAfter.some((t) => t.id === 31))

  await page.screenshot({ path: 'D:/workspace/ai-agent/verify-shots/after_delete.png', fullPage: true })

  console.log('=== CONSOLE (last 20) ===')
  console.log(consoleMsgs.slice(-20).join('\n'))
  console.log('=== PAGE ERRORS ===')
  console.log(pageErrors.join('\n') || '(none)')

  await browser.close()
  console.log('E2E_DONE')
})().catch((e) => {
  console.error('SCRIPT_ERROR:', e)
  process.exit(1)
})
