import { useCallback, useEffect, useMemo, useState } from 'react'
import { createFlammeClient } from '../../lib/flamme/client'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'
import type { GraphData, GraphNode } from '../../lib/flamme/types'
import { GraphCanvas } from './GraphCanvas'
import {
  buildDirTree,
  collapseTo,
  computeBreadcrumb,
  computeVisibleGraph,
  expandAll,
} from './hierarchy'
import { useGraphPipeline } from './useGraphPipeline'

interface GraphPanelProps {
  vaultPath: string
  keys?: FlammeKeyHeaders
  onOpenNote?: (path: string) => void
  onEnsureGraphBuilt?: () => Promise<void>
}

export function GraphPanel({
  vaultPath,
  keys,
  onOpenNote,
  onEnsureGraphBuilt,
}: GraphPanelProps) {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const [canvasKey, setCanvasKey] = useState(0)

  const client = useMemo(
    () => createFlammeClient(vaultPath, keys),
    [vaultPath, keys?.llmKey, keys?.embedKey, keys?.brainKey, keys?.mineruToken],
  )

  useGraphPipeline({
    vaultPath,
    keys,
    onEnsureGraphBuilt,
  })

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await client.getFullGraph()
      setGraphData(data)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    } finally {
      setLoading(false)
    }
  }, [client])

  useEffect(() => {
    void loadGraph()
  }, [loadGraph])

  const dirTree = useMemo(
    () => (graphData ? buildDirTree(graphData) : null),
    [graphData],
  )

  const visibleGraph = useMemo(() => {
    if (!graphData || !dirTree) return null
    return computeVisibleGraph(graphData, dirTree, expanded)
  }, [graphData, dirTree, expanded])

  const breadcrumb = useMemo(() => computeBreadcrumb(expanded), [expanded])

  const displayData = useMemo<GraphData | null>(() => {
    if (!visibleGraph) return null
    return {
      nodes: visibleGraph.nodes,
      edges: visibleGraph.edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        label: edge.count > 1 ? `${edge.label} ×${edge.count}` : edge.label,
        count: edge.count,
      })),
    }
  }, [visibleGraph])

  const rebuildGraph = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await client.buildGraph()
      setGraphData(data)
    } catch (buildError) {
      setError(buildError instanceof Error ? buildError.message : String(buildError))
    } finally {
      setLoading(false)
    }
  }

  const handleNodeDoubleClick = (node: GraphNode) => {
    if (node.isGroup && node.dirPath) {
      setExpanded((current) => {
        const next = new Set(current)
        if (next.has(node.dirPath!)) {
          for (const path of current) {
            if (path === node.dirPath || path.startsWith(`${node.dirPath}/`)) {
              next.delete(path)
            }
          }
        } else {
          next.add(node.dirPath!)
        }
        return next
      })
      setCanvasKey((value) => value + 1)
      return
    }

    const path = node.source_file || node.label
    if (path) onOpenNote?.(path)
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background" data-testid="graph-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="搜索节点…"
          className="w-40 rounded-md border border-border bg-background px-2 py-1 text-sm"
        />
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs"
          disabled={loading}
          onClick={() => void rebuildGraph()}
        >
          重建
        </button>
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs"
          onClick={() => {
            setExpanded(new Set())
            setCanvasKey((value) => value + 1)
          }}
        >
          全部折叠
        </button>
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs"
          onClick={() => {
            if (dirTree) {
              setExpanded(expandAll(dirTree))
              setCanvasKey((value) => value + 1)
            }
          }}
        >
          全部展开
        </button>
        {breadcrumb.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <button type="button" onClick={() => { setExpanded(new Set()); setCanvasKey((v) => v + 1) }}>vault</button>
            {breadcrumb.map((segment, index) => (
              <span key={segment} className="inline-flex items-center gap-1">
                /
                {index < breadcrumb.length - 1 ? (
                  <button
                    type="button"
                    onClick={() => {
                      setExpanded(collapseTo(expanded, segment))
                      setCanvasKey((value) => value + 1)
                    }}
                  >
                    {segment.split('/').pop()}
                  </button>
                ) : (
                  <span>{segment.split('/').pop()}</span>
                )}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {loading ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              加载图谱…
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              错误：{error}
            </div>
          ) : displayData && displayData.nodes.length > 0 ? (
            <GraphCanvas
              graphKey={canvasKey}
              data={displayData}
              searchQuery={searchQuery}
              onNodeClick={setSelectedNode}
              onNodeDoubleClick={handleNodeDoubleClick}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              图谱为空，请先运行图谱构建
            </div>
          )}
        </div>

        <aside className="flex w-72 shrink-0 flex-col border-l border-border bg-muted/20">
          {selectedNode ? (
            <>
              <div className="border-b border-border p-3">
                <h3 className="truncate text-sm font-semibold">
                  {selectedNode.isGroup ? '📁 ' : ''}{selectedNode.label || selectedNode.id}
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {selectedNode.isGroup
                    ? `${selectedNode.childCount ?? 0} 个文件 · 双击展开/折叠`
                    : selectedNode.source_file || selectedNode.type}
                </p>
                {!selectedNode.isGroup && selectedNode.source_file ? (
                  <button
                    type="button"
                    className="mt-2 w-full rounded-md border border-border px-2 py-1 text-xs"
                    onClick={() => onOpenNote?.(selectedNode.source_file!)}
                  >
                    打开源文件
                  </button>
                ) : null}
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center p-4 text-center text-xs text-muted-foreground">
              点击节点查看详情<br />双击分组展开<br />双击文件打开笔记
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
