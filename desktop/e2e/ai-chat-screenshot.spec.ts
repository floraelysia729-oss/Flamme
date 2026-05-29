import { test } from '@playwright/test'

test('screenshot AI chat panel', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  // Click a note item in the NoteList (x > 243, past the sidebar)
  // Note items have: cursor-pointer border-b border-[var(--border)]
  const clicked = await page.evaluate(() => {
    const items = document.querySelectorAll('[class*="cursor-pointer"]')
    for (const el of items) {
      const rect = el.getBoundingClientRect()
      // Note list items are in the middle panel (x between 250 and 700)
      if (rect.x > 249 && rect.x < 700 && rect.height > 40 && rect.width > 200) {
        (el as HTMLElement).click()
        return `Clicked: ${el.textContent?.trim().slice(0, 50)} at x=${rect.x}`
      }
    }
    return 'Nothing found'
  })
  console.log('Note click result:', clicked)
  await page.waitForTimeout(1200)

  // Now find and click the AI button in the editor toolbar
  const aiBtn = await page.evaluate(() => {
    const btns = document.querySelectorAll('button')
    for (const btn of btns) {
      if (btn.title?.includes('AI')) {
        btn.click()
        return `Clicked: ${btn.title}`
      }
    }
    return 'AI button not found'
  })
  console.log('AI btn result:', aiBtn)
  await page.waitForTimeout(800)

  await page.screenshot({ path: '/Users/luca/OpenClaw/ai-chat-final.jpg', type: 'jpeg', quality: 90 })
  console.log('Done')
})
