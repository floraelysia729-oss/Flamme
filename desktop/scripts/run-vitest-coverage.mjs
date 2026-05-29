#!/usr/bin/env node
/**
 * 前端 Vitest 覆盖率运行器
 *
 * 用途：pre-push 第 2 步，运行全部单元测试并生成覆盖率报告（门槛 ≥70%）
 *
 * 设计要点：
 * 1. 每次运行在系统临时目录创建独立 coverage 目录，避免多 worker 写入冲突
 * 2. 默认 --fileParallelism + --maxWorkers=4，平衡速度与 DOM 重套件超时
 * 3. 已知 Vitest 内部状态 flake 时自动重试一次（测试全过但 teardown 失败）
 * 4. 成功后把报告复制到项目根 coverage/，失败时保留临时目录便于调试
 *
 * 调用：pnpm test:coverage [-- 额外 vitest 参数]
 */

import { cp, mkdir, rm } from 'node:fs/promises'
import os from 'node:os'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'

const rootDir = process.cwd()
const finalCoverageDir = resolve(rootDir, 'coverage')
const coverageRunRoot = resolve(os.tmpdir(), 'tolaria-vitest-coverage-runs')
const forwardedArgs = process.argv.slice(2)
const hasFileParallelismOverride = forwardedArgs.some((arg) =>
  arg === '--fileParallelism' || arg === '--no-file-parallelism'
)
const hasMaxWorkersOverride = forwardedArgs.some((arg) =>
  arg === '--maxWorkers' || arg.startsWith('--maxWorkers=')
)
const maxAttempts = 2  // Vitest 已知 flake 时最多重试 1 次

// 独立安装的 pnpm 是原生二进制，npm_execpath 指向 Mach-O/ELF 而非 JS。
// 只有路径以 .js/.mjs/.cjs 结尾时才用 node 直接加载，否则回退到 pnpm 命令。
const packageManagerExec = process.env.npm_execpath
const isJsExecpath = packageManagerExec && /\.[mc]?js$/i.test(packageManagerExec)
const command = isJsExecpath ? process.execPath : 'pnpm'
const baseCommandArgs = isJsExecpath
  ? [packageManagerExec, 'exec', 'vitest', 'run', '--coverage']
  : ['exec', 'vitest', 'run', '--coverage']
const clearCacheCommandArgs = isJsExecpath
  ? [packageManagerExec, 'exec', 'vitest', '--clearCache']
  : ['exec', 'vitest', '--clearCache']

/** 检测 Vitest 已知内部状态 flake：测试全过但 teardown 报 "failed to access internal state" */
function isKnownVitestInternalStateFlake(output) {
  return output.includes('Vitest failed to access its internal state.')
    && /Test Files\s+\d+\s+passed\s+\(\d+\)/.test(output)
    && /Tests\s+\d+\s+passed\s+\(\d+\)/.test(output)
}

function appendCapturedOutput(output, chunk) {
  const nextOutput = output + chunk
  return nextOutput.length > 200_000 ? nextOutput.slice(-200_000) : nextOutput
}

/** 单次覆盖率运行：在临时目录隔离 worker 分片，避免并行写入冲突 */
async function runCoverageAttempt(attempt) {
  const runId = `${Date.now()}-${process.pid}-${attempt}`
  const runCoverageDir = resolve(coverageRunRoot, runId)
  const runCoverageTempDir = resolve(runCoverageDir, '.tmp')

  await mkdir(runCoverageDir, { recursive: true })
  // Vitest writes per-worker coverage shards under reportsDirectory/.tmp.
  await mkdir(runCoverageTempDir, { recursive: true })
  await clearVitestCache()

  const commandArgs = [
    ...baseCommandArgs,
    // Keep coverage fast enough for CI while avoiding the unbounded worker
    // contention that makes a few DOM-heavy suites time out under full
    // file parallelism. Callers can still opt into serial or wider runs.
    ...(hasFileParallelismOverride ? [] : ['--fileParallelism']),
    ...(hasMaxWorkersOverride ? [] : ['--maxWorkers=4']),
    `--coverage.reportsDirectory=${runCoverageDir}`,
    ...forwardedArgs,
  ]
  let output = ''

  const exitCode = await new Promise((resolveExit, rejectExit) => {
    const child = spawn(command, commandArgs, {
      cwd: rootDir,
      env: {
        ...process.env,
        VITEST_COVERAGE_DIR: runCoverageDir,
      },
      stdio: ['inherit', 'pipe', 'pipe'],
    })

    const handleOutput = (stream, target) => {
      if (!stream) return
      stream.setEncoding('utf8')
      stream.on('data', (chunk) => {
        target.write(chunk)
        output = appendCapturedOutput(output, chunk)
      })
    }

    handleOutput(child.stdout, process.stdout)
    handleOutput(child.stderr, process.stderr)

    child.on('error', rejectExit)
    child.on('exit', (code, signal) => {
      if (signal) {
        rejectExit(new Error(`Vitest coverage exited via signal: ${signal}`))
        return
      }

      resolveExit(code ?? 1)
    })
  })

  return {
    exitCode,
    output,
    runCoverageDir,
  }
}

async function clearVitestCache() {
  const exitCode = await new Promise((resolveExit, rejectExit) => {
    const child = spawn(command, clearCacheCommandArgs, {
      cwd: rootDir,
      env: process.env,
      stdio: 'inherit',
    })

    child.on('error', rejectExit)
    child.on('exit', (code, signal) => {
      if (signal) {
        rejectExit(new Error(`Vitest cache clear exited via signal: ${signal}`))
        return
      }

      resolveExit(code ?? 1)
    })
  })

  if (exitCode !== 0) {
    throw new Error(`Vitest cache clear failed with exit code ${exitCode}`)
  }
}

let finalRun = null

for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
  const run = await runCoverageAttempt(attempt)
  finalRun = run

  if (run.exitCode === 0) {
    await rm(finalCoverageDir, { recursive: true, force: true })
    await cp(run.runCoverageDir, finalCoverageDir, {
      force: true,
      recursive: true,
    })
    await rm(run.runCoverageDir, { recursive: true, force: true })
    process.exit(0)
  }

  // Retry once when Vitest itself flakes after a fully passing suite.
  if (attempt < maxAttempts && isKnownVitestInternalStateFlake(run.output)) {
    console.error(`Vitest hit a known internal-state teardown flake on attempt ${attempt}; retrying once...`)
    await rm(run.runCoverageDir, { recursive: true, force: true })
    continue
  }

  break
}

console.error(`Vitest coverage artifacts preserved at ${finalRun.runCoverageDir}`)
process.exit(finalRun.exitCode)
