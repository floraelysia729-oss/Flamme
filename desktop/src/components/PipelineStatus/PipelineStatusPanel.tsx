import { useEffect, useState } from 'react'
import { createFlammeClient } from '../../lib/flamme/client'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'
import type { PipelinePlanResponse, PipelineStatusResponse } from '../../lib/flamme/types'

const PIPELINE_POLL_MS = 30_000
const PIPELINE_POLL_EMBEDDING_MS = 5_000

interface PipelineStatusPanelProps {
  vaultPath: string
  keys?: FlammeKeyHeaders
  enabled?: boolean
  embeddingProgress?: { embedded: number; total: number } | null
}

function planScan(plan: PipelinePlanResponse | null): Record<string, unknown> | null {
  if (!plan || plan.error) return null
  const scan = plan.scan
  return scan && typeof scan === 'object' ? scan as Record<string, unknown> : null
}

function listLength(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null
}

export function PipelineStatusPanel({
  vaultPath,
  keys,
  enabled = true,
  embeddingProgress,
}: PipelineStatusPanelProps) {
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null)
  const [plan, setPlan] = useState<PipelinePlanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const embedded = embeddingProgress?.embedded ?? 0
  const total = embeddingProgress?.total ?? 0
  const embeddingActive = total > 0 && embedded < total

  useEffect(() => {
    const trimmed = vaultPath.trim()
    if (!trimmed || !enabled) {
      setStatus(null)
      setPlan(null)
      setError(null)
      return
    }

    let cancelled = false
    const client = createFlammeClient(trimmed, keys)

    const load = async () => {
      try {
        const [nextStatus, nextPlan] = await Promise.all([
          client.getPipelineStatus(),
          client.getPipelinePlan('git'),
        ])
        if (!cancelled) {
          setStatus(nextStatus)
          setPlan(nextPlan)
          setError(null)
        }
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError.message : String(fetchError))
        }
      }
    }

    void load()
    const pollMs = embeddingActive ? PIPELINE_POLL_EMBEDDING_MS : PIPELINE_POLL_MS
    const id = window.setInterval(() => {
      void load()
    }, pollMs)

    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [
    vaultPath,
    enabled,
    embeddingActive,
    keys?.llmKey,
    keys?.embedKey,
    keys?.brainKey,
    keys?.mineruToken,
  ])

  if (!enabled) {
    return <p className="text-sm text-muted-foreground">Flamme Sidecar 未连接</p>
  }

  if (error) {
    return <p className="text-sm text-muted-foreground">无法加载流水线状态：{error}</p>
  }

  if (!status) {
    return <p className="text-sm text-muted-foreground">正在加载流水线状态…</p>
  }

  const db = status.db
  const documents = db.total_documents ?? db.documents
  const scan = planScan(plan)
  const pendingIndex = listLength(scan?.md_new) ?? listLength(plan?.to_index)
  const pendingUpdated = listLength(scan?.md_updated)
  const pendingEmbed = listLength(scan?.missing_embed) ?? listLength(plan?.to_embed)
  const pendingBinary = listLength(scan?.binary_unprocessed)
  const pendingGraph = listLength(plan?.to_graph)

  return (
    <div className="space-y-3 text-sm" data-testid="pipeline-status-panel">
      <div>
        <div className="font-medium text-foreground">索引数据库</div>
        <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
          <span>文档：{documents ?? '—'}</span>
          <span>标签：{db.total_tags ?? db.entities ?? '—'}</span>
          <span>缺失文件：{db.missing_files ?? '—'}</span>
          <span>待处理：{plan?.pending_count ?? '—'}</span>
        </div>
      </div>

      {total > 0 ? (
        <div>
          <div className="font-medium text-foreground">向量嵌入</div>
          <p className="mt-1 text-muted-foreground">
            {embedded}/{total} 已完成
          </p>
          {embeddingActive ? (
            <p className="mt-1 text-xs text-muted-foreground">
              后台嵌入进行中，进度约每 5 秒刷新。
            </p>
          ) : null}
        </div>
      ) : null}

      {plan && !plan.error ? (
        <div>
          <div className="font-medium text-foreground">Git 范围待处理</div>
          <div className="mt-1 grid grid-cols-1 gap-1 text-muted-foreground">
            <span>待索引：{pendingIndex ?? pendingUpdated ?? '—'}</span>
            <span>待嵌入：{pendingEmbed ?? '—'}</span>
            <span>待摄入 PDF：{pendingBinary ?? '—'}</span>
            <span>待建图：{pendingGraph ?? '—'}</span>
          </div>
          {(pendingBinary ?? 0) > 0 ? (
            <p className="mt-2 text-xs text-muted-foreground">
              PDF 摄入（MinerU）耗时长，不会阻塞笔记编辑；仅 Chat 嵌入走 index 流水线。
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="text-xs text-muted-foreground break-all">
        Vault: {status.vault_path}
      </div>
    </div>
  )
}
