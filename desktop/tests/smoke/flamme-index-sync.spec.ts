import { test, expect } from '@playwright/test'

test.describe('Flamme pipeline status @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_documents: 3,
          by_level: {},
          total_tags: 1,
          embeddings: { embedded: 2, total: 3 },
          last_updated: null,
          vault_path: '/vault',
          vault_source: 'header',
          db_path: '/vault/.wiki/knowledge.db',
        }),
      })
    })

    await page.route('**/api/pipeline/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          db: { documents: 3, entities: 2 },
          missing_files: 0,
          git: { changed: 1 },
          baseline: 'ok',
        }),
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

  test('opens pipeline status from Flamme badge', async ({ page }) => {
    const badge = page.getByTestId('status-flamme')
    await expect(badge).toBeVisible({ timeout: 5000 })
    await badge.click()
    await expect(page.getByTestId('pipeline-status-panel')).toBeVisible({ timeout: 5000 })
  })
})
