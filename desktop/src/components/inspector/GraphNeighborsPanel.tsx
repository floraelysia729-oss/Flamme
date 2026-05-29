import { useEffect, useState } from 'react'
import { GitFork } from '@phosphor-icons/react'
import { createFlammeClient } from '../../lib/flamme/client'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'
import type { GraphNeighbor, GraphNeighborsResponse } from '../../lib/flamme/types'

interface GraphNeighborsPanelProps {
  nodeName: string | null
  vaultPath?: string
  keys?: FlammeKeyHeaders
  enabled?: boolean
  onNavigate: (target: string) => void
}

export function GraphNeighborsPanel({
  nodeName,
  vaultPath = '',
  keys,
  enabled = true,
  onNavigate,
}: GraphNeighborsPanelProps) {
  const [data, setData] = useState<GraphNeighborsResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const trimmedVault = vaultPath.trim()
    const trimmedNode = nodeName?.trim()
    if (!trimmedVault || !trimmedNode || !enabled) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    const client = createFlammeClient(trimmedVault, keys)

    void client
      .getNeighbors(trimmedNode)
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch(() => {
        if (!cancelled) {
          setData({ node: trimmedNode, neighbors: [], degree: 0, error: 'not found' })
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [vaultPath, nodeName, enabled, keys?.llmKey, keys?.embedKey, keys?.brainKey, keys?.mineruToken])

  if (!enabled) return null
  if (!nodeName?.trim()) return null

  const neighbors = data?.neighbors ?? []

  return (
    <section className="px-3 py-2" data-testid="graph-neighbors-panel">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <GitFork size={12} />
        图谱邻居
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground">加载中…</p>
      ) : neighbors.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          暂无邻居。打开知识图谱并构建索引后可显示关系。
        </p>
      ) : (
        <ul className="space-y-1">
          {neighbors.map((neighbor: GraphNeighbor) => (
            <li key={`${neighbor.id}-${neighbor.relation}`}>
              <button
                type="button"
                className="w-full rounded-sm px-1 py-0.5 text-left text-sm hover:bg-muted"
                onClick={() => onNavigate(neighbor.label || neighbor.id)}
              >
                <span className="font-medium">{neighbor.label || neighbor.id}</span>
                <span className="ml-2 text-xs text-muted-foreground">{neighbor.relation}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
