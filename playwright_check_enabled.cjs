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

  await page.goto('http://localhost/', { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => localStorage.setItem('agent-auth', s), AUTH_STATE)
  await page.goto('http://localhost/ecommerce-gallery', { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  const info = await page.evaluate(() => {
    const btn = document.querySelector('.btn-generate')
    const hint = document.querySelector('.btn-generate-hint')
    const planCount = document.querySelector('.plan-count')
    const productImgs = document.querySelectorAll('.upload-zone img, .product-upload img, [class*="upload"] img')
    return {
      btnFound: !!btn,
      btnDisabled: btn?.disabled ?? false,
      btnText: btn?.textContent?.trim().replace(/\s+/g, ' ') || '',
      hintFound: !!hint,
      hintText: hint?.textContent?.trim() || '',
      planCountText: planCount?.textContent?.trim() || '',
      productImgCount: productImgs.length,
    }
  })
  console.log('=== 上传产品图后状态（有图 + 有规划项） ===')
  console.log(JSON.stringify(info, null, 2))
  await page.screenshot({ path: 'C:/workspace/ai-agent/verify-shots/05_with_image_enabled.png', fullPage: false })

  await browser.close()
})()
