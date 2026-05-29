/**
 * Playwright Smoke 配置 — pre-push 核心 E2E 门禁
 *
 * 与 playwright.config.ts 的区别：
 * - 只跑带 @smoke 标签的测试（grep: /@smoke/）
 * - 端口 41741 + playwright-smoke-server.mjs（与 dev 5202 隔离）
 * - workers: 1 串行执行，减少 vault fixture 竞态
 * - 预置 localStorage 跳过 Claude Code  onboarding 弹窗
 *
 * 调用：pnpm playwright:smoke
 */
import { defineConfig } from '@playwright/test'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:41741'
const port = new URL(baseURL).port || '41741'
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVER
  ? process.env.PLAYWRIGHT_REUSE_SERVER === '1'
  : process.env.CI !== 'true'
const claudeCodeOnboardingStorageState = {
  cookies: [],
  origins: [
    {
      origin: baseURL,
      localStorage: [
        { name: 'tolaria:claude-code-onboarding-dismissed', value: '1' },
      ],
    },
  ],
}

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 1,
  workers: 1,
  grep: /@smoke/,
  use: {
    baseURL,
    headless: true,
    storageState: claudeCodeOnboardingStorageState,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: `node scripts/playwright-smoke-server.mjs ${port}`,
    url: baseURL,
    reuseExistingServer,
    timeout: 30_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
