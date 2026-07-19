const { chromium } = require('playwright')

const BASE = 'http://localhost/'
const API = 'http://localhost:8010'

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })

  const login = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' }),
  }).then((r) => r.json())
  const token = login.access_token
  const user = login.user
  await page.addInitScript(
    ([tk, u]) => {
      localStorage.setItem('agent-auth', JSON.stringify({ state: { token: tk, user: u, isAuthenticated: true }, version: 0 }))
    },
    [token, user],
  )

  const errors = []
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()) })

  await page.goto(BASE + 'ecommerce-gallery', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)

  // 1) 切换到创作案例
  await page.locator('.area-tab', { hasText: '创作案例' }).click()
  await page.waitForSelector('.case-card', { timeout: 15000 })
  await page.waitForTimeout(800)

  const card = page.locator('.case-card').first()

  // 2) 默认态（未 hover）：用 computed opacity 判定，避免 isVisible 受过渡影响
  console.log('--- 默认态检查 ---')
  const op = (sel) => page.evaluate((s) => {
    const el = document.querySelector(s)
    if (!el) return null
    return parseFloat(getComputedStyle(el).opacity) || 0
  }, sel)
  const badgeOp = await op('.case-card .case-count-badge')
  const samplesOp = await op('.case-card .case-samples')
  const origOp = await op('.case-card .case-orig-thumb .orig-label')
  console.log('默认徽章 opacity', badgeOp, badgeOp > 0.5 ? 'OK(可见)' : 'FAIL')
  console.log('默认样图 opacity', samplesOp, samplesOp < 0.5 ? 'OK(隐藏)' : 'FAIL')
  console.log('默认原图标签 opacity', origOp, origOp < 0.5 ? 'OK(隐藏)' : 'FAIL')
  const viewText = await card.locator('.case-view-btn').textContent()
  console.log('默认按钮文案', JSON.stringify(viewText), viewText.trim() === '查看详情' ? 'OK' : 'FAIL')
  const styleHiddenDefault = (await card.locator('.case-style-btn').isVisible().catch(() => true)) === false
  console.log('默认不显示立即生成同款', styleHiddenDefault ? 'OK' : 'FAIL')
  await card.scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'verify-shots/case_card_default.png' })
  await page.mouse.move(0, 0)
  await page.waitForTimeout(300)

  // 3) hover 态：用 computed opacity 判定
  await card.hover()
  await page.waitForTimeout(600)
  console.log('--- hover 态检查 ---')
  const samplesOpHover = await op('.case-card .case-samples')
  console.log('hover 样图 opacity', samplesOpHover, samplesOpHover > 0.5 ? 'OK(可见)' : 'FAIL')
  const badgeOpHover = await op('.case-card .case-count-badge')
  console.log('hover 徽章 opacity', badgeOpHover, badgeOpHover < 0.5 ? 'OK(隐藏)' : 'FAIL')
  const origOpHover = await op('.case-card .case-orig-thumb .orig-label')
  console.log('hover 原图标签 opacity', origOpHover, origOpHover > 0.5 ? 'OK(可见)' : 'FAIL')
  const styleText = await card.locator('.case-style-btn').textContent()
  console.log('hover 按钮文案', JSON.stringify(styleText), styleText.trim() === '立即生成同款' ? 'OK' : 'FAIL')
  const totalText = await card.locator('.case-samples .case-total').textContent().catch(() => '')
  console.log('hover 总数卡片文案', JSON.stringify(totalText), /^\+\d+$/.test(totalText.trim()) ? 'OK' : 'FAIL')
  const sampleRotate = await page.evaluate(() => {
    const el = document.querySelector('.case-card .case-samples img.sample-1')
    if (!el) return null
    const m = getComputedStyle(el).transform
    return m
  })
  console.log('hover 中间样图有旋转', sampleRotate, (sampleRotate && sampleRotate !== 'none' && sampleRotate !== 'matrix(1, 0, 0, 1, 0, 0)') ? 'OK' : 'FAIL')
  await page.screenshot({ path: 'verify-shots/case_card_hover.png' })

  // 4) 点击 立即生成同款 → 弹出创作案例详情
  await card.locator('.case-style-btn').click()
  const caseModal = page.locator('.ant-modal').filter({ hasText: '创作案例详情' })
  await caseModal.waitFor({ timeout: 10000 })
  await page.waitForTimeout(500)
  const caseActionText = await caseModal.locator('.detail-actions').innerText().catch(() => '')
  const hasSameStyle = /一键做同款/.test(caseActionText)
  const btnBg = await caseModal.locator('.detail-actions .btn-primary').evaluate((el) => getComputedStyle(el).backgroundColor).catch(() => '')
  console.log('--- 创作案例详情弹框检查 ---')
  console.log('详情弹框操作区文案', JSON.stringify(caseActionText), hasSameStyle ? 'OK(有一键做同款)' : 'FAIL')
  console.log('一键做同款按钮底色', btnBg, (btnBg && btnBg !== 'rgba(0, 0, 0, 0)' && btnBg !== 'transparent') ? 'OK(有底色,白字清晰)' : 'FAIL')
  await page.screenshot({ path: 'verify-shots/case_detail_modal.png' })

  // 5) 点击详情页里的 一键做同款（验证按钮存在且可点击，不报错）
  const sameStyleInModal = caseModal.locator('.btn-primary')
  let clicked = false
  try {
    await sameStyleInModal.click({ timeout: 8000 })
    clicked = true
    await page.waitForTimeout(800)
  } catch (e) {
    clicked = false
  }
  console.log('点击详情页一键做同款', clicked ? 'OK(可点击)' : 'FAIL')
  // 关闭可能打开或已关闭的弹框
  const closeBtn = caseModal.locator('.btn-secondary', { hasText: '关闭' })
  if ((await closeBtn.count()) > 0) {
    await closeBtn.first().click().catch(() => {})
    await page.waitForTimeout(300)
  }

  // 6) 任务结果详情弹框：检查有一键做同款按钮（若有任务）
  await page.locator('.area-tab', { hasText: '创作结果' }).click()
  await page.waitForTimeout(1000)
  const taskCard = page.locator('.task-card').filter({ has: page.locator('.cell-caption-text') }).first()
  const taskCardCount = await taskCard.count()
  if (taskCardCount === 0) {
    console.log('--- 任务结果详情弹框检查 ---')
    console.log('当前无任务卡片，跳过')
  } else {
    await taskCard.scrollIntoViewIfNeeded()
    await page.waitForTimeout(200)
    const viewBtn = taskCard.locator('.task-actions .btn').filter({ hasText: '查看详情' })
    await viewBtn.click()
    const taskModal = page.locator('.ant-modal').filter({ hasText: '生成结果详情' })
    await taskModal.waitFor({ timeout: 10000 })
    await page.waitForTimeout(500)
    const taskActionText = await taskModal.locator('.detail-actions').innerText().catch(() => '')
    const hasSameStyleTask = /一键做同款/.test(taskActionText)
    console.log('--- 任务结果详情弹框检查 ---')
    console.log('操作区文案', JSON.stringify(taskActionText), hasSameStyleTask ? 'OK(有一键做同款)' : 'FAIL')
    await page.screenshot({ path: 'verify-shots/task_detail_clean.png' })
  }

  console.log('PAGE ERRORS:', errors.length ? errors.join(' | ') : 'none')
  await browser.close()
})().catch((e) => { console.error('E2E FAILED:', e); process.exit(1) })
