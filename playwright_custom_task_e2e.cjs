const { chromium } = require('playwright')
const fs = require('fs')

const TOKEN = process.env.GALLERY_TOKEN || fs.readFileSync('/tmp/gallery_token.txt', 'utf8').trim().split('=')[1]
const USER = { id: 1, email: 'admin@example.com', username: 'admin', role: 'admin' }

const AUTH_STATE = JSON.stringify({
  state: { token: TOKEN, user: USER, isAuthenticated: true },
  version: 0,
})

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const consoleMsgs = []
  const pageErrors = []
  page.on('console', (m) => consoleMsgs.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  // 注入 localStorage 免登录
  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  // 检查"立即生成"按钮状态和禁用提示
  const initialInfo = await page.evaluate(() => {
    const btn = document.querySelector('.btn-generate')
    const hint = document.querySelector('.btn-generate-hint')
    return {
      btnFound: !!btn,
      btnDisabled: btn?.disabled ?? false,
      btnText: btn?.textContent?.trim().replace(/\s+/g, ' ') || '',
      hintFound: !!hint,
      hintText: hint?.textContent?.trim() || '',
    }
  })
  console.log('=== 初始状态（无产品图、无规划项） ===')
  console.log(JSON.stringify(initialInfo, null, 2))
  await page.screenshot({ path: 'C:/workspace/ai-agent/verify-shots/01_initial_disabled.png', fullPage: false })

  // 打开策划抽屉
  await page.click('.btn-plan-ai, .btn-plan-add')
  await page.waitForTimeout(800)
  await page.screenshot({ path: 'C:/workspace/ai-agent/verify-shots/02_drawer_open.png', fullPage: false })

  // 切到"自定义子任务"tab
  const tabs = await page.locator('.drawer-tab').allInnerTexts()
  console.log('抽屉 tabs:', tabs)
  const customTab = page.locator('.drawer-tab', { hasText: '自定义子任务' }).first()
  await customTab.click()
  await page.waitForTimeout(500)

  // 填写表单（必须限定在抽屉内的 .custom-task-form，避免误填页面其它 textarea）
  await page.locator('.custom-task-form textarea').first().fill('测试自定义任务需求描述', { timeout: 3000 })

  // 截图：自定义子任务表单
  await page.screenshot({ path: 'C:/workspace/ai-agent/verify-shots/03_custom_form.png', fullPage: false })

  // 点击"确认添加任务"
  const submitBtn = page.locator('.ctf-submit').first()
  const submitDisabled = await submitBtn.evaluate((el) => el.disabled)
  console.log('确认添加任务按钮 disabled:', submitDisabled)
  await submitBtn.click()

  // 等待请求完成和消息提示
  await page.waitForTimeout(3000)

  // 检查抽屉是否关闭、按钮状态、禁用提示
  const afterInfo = await page.evaluate(() => {
    const btn = document.querySelector('.btn-generate')
    const hint = document.querySelector('.btn-generate-hint')
    const drawer = document.querySelector('.ant-drawer-open')
    return {
      drawerOpen: !!drawer,
      btnFound: !!btn,
      btnDisabled: btn?.disabled ?? false,
      btnText: btn?.textContent?.trim().replace(/\s+/g, ' ') || '',
      hintFound: !!hint,
      hintText: hint?.textContent?.trim() || '',
    }
  })
  console.log('=== 添加自定义子任务后状态 ===')
  console.log(JSON.stringify(afterInfo, null, 2))
  await page.screenshot({ path: 'C:/workspace/ai-agent/verify-shots/04_after_custom_added.png', fullPage: false })

  // 输出控制台消息
  if (consoleMsgs.length) {
    console.log('=== Console Messages ===')
    consoleMsgs.forEach((m) => console.log(m))
  }
  if (pageErrors.length) {
    console.log('=== Page Errors ===')
    pageErrors.forEach((e) => console.log(e))
  }

  await browser.close()
})()
