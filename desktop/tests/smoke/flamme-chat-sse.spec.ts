import { test, expect } from '@playwright/test'

test.describe('Flamme chat SSE @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/chat', async (route) => {
      const body = [
        'data: {"type":"token","content":"Hello from Flamme"}\n',
        '\n',
        'data: {"type":"done"}\n',
        '\n',
      ].join('')
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body,
      })
    })

    await page.route('**/api/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_documents: 1,
          by_level: {},
          total_tags: 0,
          embeddings: { embedded: 1, total: 1 },
          last_updated: null,
          vault_path: '/vault',
          vault_source: 'header',
          db_path: '/vault/.wiki/knowledge.db',
        }),
      })
    })

    await page.route('**/api/pipeline/run', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', preset: 'index', scope: 'git' }),
      })
    })

    await page.route('http://127.0.0.1:8765/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ name: 'Flamme', status: 'ok' }),
      })
    })

    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('[data-testid="note-list-container"]')).toBeVisible({ timeout: 5_000 })
  })

  test('sends chat and renders Flamme SSE response', async ({ page }) => {
    const noteItem = page.locator('.app__note-list .cursor-pointer').first()
    await noteItem.click()

    await page.getByRole('button', { name: 'Open the AI panel' }).click()
    await expect(page.getByTestId('ai-panel')).toBeVisible({ timeout: 3000 })

    const input = page.getByTestId('agent-input')
    await input.fill('test flamme message')
    await page.getByTestId('agent-send').click()

    await expect(page.getByTestId('ai-message').first()).toContainText('Hello from Flamme', { timeout: 5000 })
  })
})
