#!/usr/bin/env node
/**
 * Playwright Smoke 测试专用开发服务器
 *
 * 用途：pre-push smoke 套件启动 Vite dev server，与日常 pnpm dev 隔离
 *
 * 为什么单独脚本：
 * - smoke 使用固定端口 41741（见 playwright.smoke.config.ts），避免与 dev 5202 冲突
 * - --strictPort 确保端口被占用时立即失败，而非静默换端口
 * - 转发 SIGINT/SIGTERM 给子进程，Playwright 结束时干净退出 Vite
 *
 * 调用：node scripts/playwright-smoke-server.mjs [端口]
 */

import { spawn } from 'node:child_process'

// 端口优先级：命令行参数 > 环境变量 PORT > 默认 41741
const port = process.argv[2] ?? process.env.PORT ?? '41741'

const child = spawn(
  'pnpm',
  ['dev', '--host', '127.0.0.1', '--port', port, '--strictPort'],
  {
    cwd: process.cwd(),
    env: process.env,
    stdio: ['pipe', 'inherit', 'inherit'],
  },
)

// 将 Playwright 收到的终止信号转发给 Vite 子进程，避免僵尸进程
function forwardSignal(signal) {
  if (child.killed) return
  child.kill(signal)
}

process.on('SIGINT', () => forwardSignal('SIGINT'))
process.on('SIGTERM', () => forwardSignal('SIGTERM'))

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
    return
  }

  process.exit(code ?? 1)
})
