import { useEffect, useState } from 'react'
import { createFlammeClient } from '../../lib/flamme/client'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'
import type { PipelineStatusResponse } from '../../lib/flamme/types'

interface PipelineStatusSummaryProps {
  vaultPath: string
  keys?: FlammeKeyHeaders
  enabled?: boolean
}

export function PipelineStatusSummary({
  vaultPath,
  keys,
  enabled = true,
}: PipelineStatusSummaryProps) {
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const trimmed = vaultPath.trim()
    if (!trimmed || !enabled) {
      setStatus(null)
      setError(null)
      return
    }

    let cancelled = false
    const client = createFlammeClient(trimmed, keys)

    void client
      .getPipelineStatus()
      .then((result) => {
        if (!cancelled) {
          setStatus(result)
          setError(null)
        }
      })
      .catch((fetchError) => {
        if (!cancelled) {
          setStatus(null)
          setError(fetchError instanceof Error ? fetchError.message : String(fetchError))
        }
      })

    return () => {
      cancelled = true
    }
  }, [vaultPath, enabled, keys?.llmKey, keys?.embedKey, keys?.brainKey, keys?.mineruToken])

  if (!enabled) {
    return (
      <p className="text-xs text-muted-foreground">Flamme Sidecar 未连接</p>
    )
  }

  if (error) {
    return (
      <p className="text-xs text-muted-foreground">索引状态不可用：{error}</p>
    )
  }

  if (!status) {
    return (
      <p className="text-xs text-muted-foreground">正在加载索引状态…</p>
    )
  }

  const docs = status.db.documents ?? '—'
  const entities = status.db.entities ?? '—'
  const missing = status.db.missing_files ?? '—'

  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
      <div className="font-medium text-foreground">索引概览</div>
      <div className="mt-1 grid grid-cols-3 gap-2">
        <span>文档 {String(docs)}</span>
        <span>实体 {String(entities)}</span>
        <span>缺失 {String(missing)}</span>
      </div>
    </div>
  )
}
