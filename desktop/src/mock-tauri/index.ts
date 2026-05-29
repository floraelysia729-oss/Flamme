/**
 * Mock Tauri invoke — 浏览器/Playwright 环境下的 IPC 降级层
 *
 * 当不在 Tauri 桌面壳内运行时（如 Chrome localhost、Playwright smoke），
 * 用 mock 数据或 HTTP API 替代 Rust 后端，使 UI 可独立开发和测试。
 *
 * 降级优先级：
 *   1. tryVaultApi — 若 /api/vault/ping 可用，走 HTTP（serve-demo.mjs 或 Python 后端）
 *   2. mockHandlers — 硬编码 mock 数据
 *   3. window.__mockHandlers — Playwright 注入的自定义 handler
 *
 * 检测 Tauri：window.__TAURI__ 或 __TAURI_INTERNALS__ 存在即为桌面环境
 */

import { MOCK_CONTENT } from './mock-content'
import { mockHandlers, addMockEntry, updateMockContent, trackMockChange } from './mock-handlers'
import { tryVaultApi } from './vault-api'

export { addMockEntry, updateMockContent, trackMockChange }

type MockHandler = (args: Record<string, unknown> | undefined) => unknown

export function isTauri(): boolean {
  if (typeof globalThis !== 'undefined' && typeof (globalThis as { isTauri?: unknown }).isTauri === 'boolean') {
    return Boolean((globalThis as { isTauri?: unknown }).isTauri)
  }

  return typeof window !== 'undefined' && ('__TAURI__' in window || '__TAURI_INTERNALS__' in window)
}

// Initialize window globals for browser testing and Playwright overrides
if (typeof window !== 'undefined') {
  window.__mockContent = MOCK_CONTENT
  window.__mockHandlers = mockHandlers
}

function resolveMockHandler(command: string) {
  const windowHandler = typeof window === 'undefined' || !window.__mockHandlers
    ? undefined
    : Reflect.get(window.__mockHandlers, command) as MockHandler | undefined
  return windowHandler ?? Reflect.get(mockHandlers, command) as MockHandler | undefined
}

export async function mockInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const vaultResult = await tryVaultApi<T>(cmd, args)
  if (vaultResult !== undefined) return vaultResult

  const handler = resolveMockHandler(cmd)
  if (handler) {
    await new Promise((r) => setTimeout(r, 100))
    return handler(args) as T
  }
  throw new Error(`No mock handler for command: ${cmd}`)
}
