/**
 * Vault HTTP API 代理 — Flamme 3.0 已禁用
 *
 * Markdown CRUD 永远走 Rust invoke（Tauri）或 mock-handlers（浏览器 dev）。
 * Python Flamme 后端不提供 /api/vault/* 路由。
 */

export async function tryVaultApi<T>(_cmd: string, _args?: Record<string, unknown>): Promise<T | undefined> {
  return undefined
}
