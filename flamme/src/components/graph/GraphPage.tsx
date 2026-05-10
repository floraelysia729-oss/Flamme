import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from '../../lib/api'

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    api.graph.full()
      .then(data => setGraphData(data))
      .catch(() => setGraphData(null))
      .finally(() => setLoading(false))
  }, [])

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node)
  }, [])

  if (loading) {
    return <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-200)' }}>加载图谱...</div>
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-200)' }}>
        <p>图谱为空，请先运行图谱构建</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      {/* 图谱主区域 */}
      <div style={{ flex: 1, position: 'relative' }}>
        {/* 搜索栏 */}
        <div style={{
          position: 'absolute',
          top: 16,
          left: 16,
          zIndex: 10,
          display: 'flex',
          gap: 8,
        }}>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索节点..."
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid var(--bg-300)',
              background: '#fff',
              fontSize: 13,
              width: 200,
            }}
          />
        </div>

        {/* Force Graph 容器 */}
        <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
          <GraphCanvas
            data={graphData}
            searchQuery={searchQuery}
            onNodeClick={handleNodeClick}
          />
        </div>
      </div>

      {/* 节点详情面板 */}
      <div style={{
        width: 280,
        padding: 16,
        background: 'var(--bg-200)',
        borderLeft: '1px solid var(--bg-300)',
        overflow: 'auto',
      }}>
        {selectedNode ? (
          <>
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
              {selectedNode.label || selectedNode.id}
            </h3>
            <div style={{ fontSize: 13, color: 'var(--text-200)' }}>
              <p>类型: {selectedNode.type || '-'}</p>
              <p>级别: {selectedNode.level || '-'}</p>
              <p>连接数: {selectedNode.val || 0}</p>
            </div>
          </>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--text-200)' }}>点击节点查看详情</p>
        )}
      </div>
    </div>
  )
}

/** Canvas 渲染的图谱 — 使用 Canvas 2D 绘制力导向图 */
function GraphCanvas({ data, searchQuery, onNodeClick }: {
  data: { nodes: any[]; edges: any[] }
  searchQuery: string
  onNodeClick: (node: any) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hovered, setHovered] = useState<string | null>(null)

  // 简化的力导向模拟 + Canvas 渲染
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const rect = canvas.parentElement!.getBoundingClientRect()
    canvas.width = rect.width * window.devicePixelRatio
    canvas.height = rect.height * window.devicePixelRatio
    canvas.style.width = rect.width + 'px'
    canvas.style.height = rect.height + 'px'
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio)

    const w = rect.width
    const h = rect.height

    // 初始化节点位置
    const nodes = data.nodes.map((n, i) => ({
      ...n,
      x: w / 2 + Math.cos(i * 2.4) * Math.min(w, h) * 0.3,
      y: h / 2 + Math.sin(i * 2.4) * Math.min(w, h) * 0.3,
      vx: 0,
      vy: 0,
    }))
    const nodeMap = new Map(nodes.map(n => [n.id, n]))

    const edges = data.edges.map(e => ({
      source: nodeMap.get(e.source),
      target: nodeMap.get(e.target),
      label: e.label || '',
    })).filter(e => e.source && e.target)

    // 颜色映射
    const getColor = (type: string) => {
      switch (type) {
        case 'entity': return '#EE6C4D'
        case 'topic': return '#927156'
        default: return '#5c5c5c'
      }
    }

    // 简单力模拟（若干轮）
    for (let iter = 0; iter < 120; iter++) {
      for (const edge of edges) {
        const dx = (edge.target!.x - edge.source!.x) || 0.01
        const dy = (edge.target!.y - edge.source!.y) || 0.01
        const dist = Math.sqrt(dx * dx + dy * dy)
        const force = (dist - 100) * 0.005
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        edge.source!.vx += fx
        edge.source!.vy += fy
        edge.target!.vx -= fx
        edge.target!.vy -= fy
      }
      // 排斥
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x || 0.01
          const dy = nodes[j].y - nodes[i].y || 0.01
          const dist = Math.sqrt(dx * dx + dy * dy)
          const force = -3000 / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          nodes[i].vx += fx
          nodes[i].vy += fy
          nodes[j].vx -= fx
          nodes[j].vy -= fy
        }
      }
      // 向中心吸引
      for (const n of nodes) {
        n.vx += (w / 2 - n.x) * 0.001
        n.vy += (h / 2 - n.y) * 0.001
        n.x += n.vx * 0.3
        n.y += n.vy * 0.3
        n.vx *= 0.9
        n.vy *= 0.9
      }
    }

    // 渲染
    const draw = () => {
      ctx.clearRect(0, 0, w, h)

      // 边
      ctx.strokeStyle = '#c1caca'
      ctx.lineWidth = 0.5
      for (const edge of edges) {
        ctx.beginPath()
        ctx.moveTo(edge.source!.x, edge.source!.y)
        ctx.lineTo(edge.target!.x, edge.target!.y)
        ctx.stroke()
      }

      // 节点
      for (const node of nodes) {
        const isHovered = hovered === node.id
        const isSearchMatch = searchQuery &&
          (node.label || node.id).toLowerCase().includes(searchQuery.toLowerCase())

        const r = Math.max(4, Math.min(16, (node.val || 1) * 1.5))
        const color = getColor(node.type)

        ctx.beginPath()
        ctx.arc(node.x, node.y, isHovered ? r + 3 : isSearchMatch ? r + 2 : r, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = isSearchMatch ? 1 : searchQuery ? 0.3 : isHovered ? 1 : 0.8
        ctx.fill()
        ctx.globalAlpha = 1

        // 标签
        if (r > 5 || isHovered || isSearchMatch) {
          ctx.fillStyle = 'var(--text-100)'
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText(node.label || node.id, node.x, node.y + r + 12)
        }
      }
    }
    draw()

    // 鼠标交互
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      let found = null
      for (const node of nodes) {
        const dx = mx - node.x
        const dy = my - node.y
        const r = Math.max(4, Math.min(16, (node.val || 1) * 1.5))
        if (dx * dx + dy * dy < (r + 4) * (r + 4)) {
          found = node.id
          break
        }
      }
      if (found !== hovered) {
        setHovered(found)
        draw()
      }
    }

    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      for (const node of nodes) {
        const dx = mx - node.x
        const dy = my - node.y
        const r = Math.max(4, Math.min(16, (node.val || 1) * 1.5))
        if (dx * dx + dy * dy < (r + 4) * (r + 4)) {
          onNodeClick(node)
          break
        }
      }
    }

    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('click', handleClick)
    return () => {
      canvas.removeEventListener('mousemove', handleMouseMove)
      canvas.removeEventListener('click', handleClick)
    }
  }, [data, searchQuery, hovered, onNodeClick])

  return <canvas ref={canvasRef} style={{ display: 'block' }} />
}
