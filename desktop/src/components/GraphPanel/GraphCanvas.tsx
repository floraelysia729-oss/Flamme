import dagre from 'dagre'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { GraphData, GraphNode } from '../../lib/flamme/types'

const COLORS = [
  '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
  '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
]

interface LayoutNode extends GraphNode {
  x: number
  y: number
  width: number
  height: number
}

interface LayoutEdge {
  source: string
  target: string
  label: string
  count: number
  points: { x: number; y: number }[]
}

interface GraphCanvasProps {
  graphKey?: number
  data: GraphData
  searchQuery?: string
  onNodeClick?: (node: GraphNode) => void
  onNodeDoubleClick?: (node: GraphNode) => void
}

function nodeColor(node: GraphNode): string {
  if (node.isGroup) {
    const hash = (node.dirPath || node.id).split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
    return COLORS[hash % COLORS.length]
  }
  return COLORS[(node.community ?? 0) % COLORS.length]
}

function edgePathD(points: { x: number; y: number }[]): string {
  if (points.length < 2) return ''
  if (points.length === 2) {
    const [p0, p1] = points
    const mx = (p0.x + p1.x) / 2
    const my = (p0.y + p1.y) / 2
    const dx = p1.x - p0.x
    const dy = p1.y - p0.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    const offset = Math.min(dist * 0.15, 30)
    const nx = -dy / (dist || 1) * offset
    const ny = dx / (dist || 1) * offset
    return `M${p0.x},${p0.y} Q${mx + nx},${my + ny} ${p1.x},${p1.y}`
  }
  let path = `M${points[0].x},${points[0].y}`
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1]
    const curr = points[index]
    const cpx = (prev.x + curr.x) / 2
    const cpy = (prev.y + curr.y) / 2
    path += ` Q${cpx},${cpy} ${curr.x},${curr.y}`
  }
  return path
}

function computeLayout(data: GraphData): {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
} {
  if (!data.nodes.length) return { nodes: [], edges: [] }

  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70, marginx: 40, marginy: 40 })
  graph.setDefaultEdgeLabel(() => ({}))

  for (const node of data.nodes) {
    const label = node.label || node.id
    if (node.isGroup) {
      const width = Math.max(120, Math.min(220, label.length * 12 + 80))
      graph.setNode(node.id, { label, width, height: 48 })
    } else {
      const width = Math.max(80, Math.min(180, label.length * 9 + 24))
      graph.setNode(node.id, { label, width, height: 32 })
    }
  }

  for (const edge of data.edges) {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.setEdge(edge.source, edge.target, {})
    }
  }

  dagre.layout(graph)

  const nodes = data.nodes.map((node): LayoutNode => {
    const pos = graph.node(node.id)
    return { ...node, x: pos.x, y: pos.y, width: pos.width, height: pos.height }
  })

  const edges = data.edges
    .filter((edge) => graph.hasNode(edge.source) && graph.hasNode(edge.target))
    .map((edge): LayoutEdge => {
      const layoutEdge = graph.edge(edge.source, edge.target)
      return {
        source: edge.source,
        target: edge.target,
        label: edge.label || '',
        count: edge.count || 1,
        points: layoutEdge.points,
      }
    })

  return { nodes, edges }
}

export function GraphCanvas({
  graphKey = 0,
  data,
  searchQuery = '',
  onNodeClick,
  onNodeDoubleClick,
}: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [transform, setTransform] = useState({ tx: 0, ty: 0, scale: 1 })
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const panRef = useRef<{ active: boolean; startX: number; startY: number; tx: number; ty: number }>({
    active: false,
    startX: 0,
    startY: 0,
    tx: 0,
    ty: 0,
  })

  const layout = useMemo(() => computeLayout(data), [data])
  const normalizedQuery = searchQuery.trim().toLowerCase()

  useEffect(() => {
    const svg = svgRef.current
    if (!svg || layout.nodes.length === 0) return

    const rect = svg.getBoundingClientRect()
    const xs = layout.nodes.map((node) => node.x)
    const ys = layout.nodes.map((node) => node.y)
    const minX = Math.min(...xs) - 80
    const maxX = Math.max(...xs) + 80
    const minY = Math.min(...ys) - 60
    const maxY = Math.max(...ys) + 60
    const graphW = maxX - minX
    const graphH = maxY - minY
    const pad = 0.85
    const scaleX = (rect.width * pad) / graphW
    const scaleY = (rect.height * pad) / graphH
    const scale = Math.min(scaleX, scaleY, 2)
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    setTransform({
      tx: rect.width / 2 - cx * scale,
      ty: rect.height / 2 - cy * scale,
      scale,
    })
  }, [graphKey, layout.nodes])

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    panRef.current = {
      active: true,
      startX: event.clientX,
      startY: event.clientY,
      tx: transform.tx,
      ty: transform.ty,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!panRef.current.active) return
    setTransform((current) => ({
      ...current,
      tx: panRef.current.tx + (event.clientX - panRef.current.startX),
      ty: panRef.current.ty + (event.clientY - panRef.current.startY),
    }))
  }

  const onPointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    panRef.current.active = false
    event.currentTarget.releasePointerCapture(event.pointerId)
  }

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault()
    const factor = event.deltaY > 0 ? 0.9 : 1.1
    setTransform((current) => ({
      ...current,
      scale: Math.max(0.2, Math.min(3, current.scale * factor)),
    }))
  }

  return (
    <svg
      ref={svgRef}
      className="h-full w-full touch-none bg-background"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
    >
      <g transform={`translate(${transform.tx},${transform.ty}) scale(${transform.scale})`}>
        {layout.edges.map((edge) => (
          <path
            key={`${edge.source}-${edge.target}-${edge.label}`}
            d={edgePathD(edge.points)}
            fill="none"
            stroke="var(--border)"
            strokeWidth={Math.min(1 + edge.count * 0.5, 4)}
            opacity={0.7}
          />
        ))}
        {layout.nodes.map((node) => {
          const label = node.label || node.id
          const matches = !normalizedQuery || label.toLowerCase().includes(normalizedQuery)
          const fill = nodeColor(node)
          const highlighted = hoveredId === node.id || (normalizedQuery.length > 0 && matches)
          return (
            <g
              key={node.id}
              transform={`translate(${node.x - node.width / 2},${node.y - node.height / 2})`}
              onMouseEnter={() => setHoveredId(node.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onNodeClick?.(node)}
              onDoubleClick={() => onNodeDoubleClick?.(node)}
              style={{ cursor: 'pointer', opacity: normalizedQuery && !matches ? 0.25 : 1 }}
            >
              <rect
                width={node.width}
                height={node.height}
                rx={node.isGroup ? 8 : 4}
                fill={fill}
                stroke={highlighted ? 'var(--foreground)' : 'transparent'}
                strokeWidth={highlighted ? 2 : 0}
              />
              <text
                x={node.width / 2}
                y={node.height / 2 + 4}
                textAnchor="middle"
                fontSize={node.isGroup ? 12 : 11}
                fill="#fff"
                pointerEvents="none"
              >
                {label.length > 18 ? `${label.slice(0, 16)}…` : label}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
