import { test, expect } from '@playwright/test'

test.describe('Flamme graph panel @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_documents: 2,
          by_level: {},
          total_tags: 0,
          embeddings: { embedded: 2, total: 2 },
          last_updated: null,
          vault_path: '/vault',
          vault_source: 'header',
          db_path: '/vault/.wiki/knowledge.db',
        }),
      })
    })

    await page.route('**/api/graph/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ nodes: 2, edges: 1, entities: 2 }),
      })
    })

    await page.route('**/api/graph/full', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [
            { id: 'A', label: 'Node A', type: 'entity', source_file: 'entities/A.md' },
            { id: 'B', label: 'Node B', type: 'entity', source_file: 'entities/B.md' },
          ],
          edges: [{ source: 'A', target: 'B', relation: 'related_to' }],
        }),
      })
    })

    await page.route('**/api/pipeline/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
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

  test('opens graph view and renders nodes', async ({ page }) => {
    await page.getByRole('button', { name: '知识图谱' }).click()
    await expect(page.getByTestId('graph-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-testid="graph-panel"] text')).toContainText('Node A', { timeout: 5000 })
  })
})
