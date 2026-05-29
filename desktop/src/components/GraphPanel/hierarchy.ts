import type { AggregatedEdge, DirNode, GraphData, GraphEdge, GraphNode } from '../../lib/flamme/types'

export function buildDirTree(data: GraphData): DirNode {
  const root: DirNode = { id: '', label: 'vault', children: [], leafNodeIds: [], totalCount: 0 }

  for (const node of data.nodes) {
    const path = node.source_file || node.entity_file || ''
    const dirPath = extractDirPath(path)
    const dirNode = ensureDirChain(root, dirPath)
    dirNode.leafNodeIds.push(node.id)
  }

  computeTotalCount(root)
  return root
}

function extractDirPath(filePath: string): string {
  if (!filePath) return '(global)'
  const lastSlash = filePath.lastIndexOf('/')
  if (lastSlash <= 0) return ''
  return filePath.substring(0, lastSlash)
}

function ensureDirChain(root: DirNode, dirPath: string): DirNode {
  if (!dirPath || dirPath === '(global)') {
    let globalDir = root.children.find((child) => child.id === '(global)')
    if (!globalDir) {
      globalDir = { id: '(global)', label: '(global)', children: [], leafNodeIds: [], totalCount: 0 }
      root.children.push(globalDir)
    }
    return globalDir
  }

  const segments = dirPath.split('/')
  let current = root

  for (let index = 0; index < segments.length; index += 1) {
    const segId = segments.slice(0, index + 1).join('/')
    let child = current.children.find((candidate) => candidate.id === segId)
    if (!child) {
      child = { id: segId, label: segments[index], children: [], leafNodeIds: [], totalCount: 0 }
      current.children.push(child)
    }
    current = child
  }

  return current
}

function computeTotalCount(node: DirNode): number {
  let count = node.leafNodeIds.length
  for (const child of node.children) {
    count += computeTotalCount(child)
  }
  node.totalCount = count
  return count
}

export function computeVisibleGraph(
  data: GraphData,
  dirTree: DirNode,
  expanded: Set<string>,
): { nodes: GraphNode[]; edges: AggregatedEdge[] } {
  const nodeMap = new Map<string, GraphNode>()
  for (const node of data.nodes) {
    nodeMap.set(node.id, node)
  }

  const visibleNodes: GraphNode[] = []
  const groupNodes: GraphNode[] = []

  function walk(dir: DirNode, depth: number) {
    if (depth === 0) {
      for (const child of dir.children) {
        collectVisible(child, 1)
      }
    }
  }

  function collectVisible(dir: DirNode, depth: number) {
    void depth
    const isExpanded = expanded.has(dir.id)

    if (!isExpanded) {
      groupNodes.push({
        id: `group::${dir.id}`,
        label: dir.label,
        type: 'group',
        isGroup: true,
        childCount: dir.totalCount,
        dirPath: dir.id,
      })
      return
    }

    for (const child of dir.children) {
      collectVisible(child, depth + 1)
    }

    for (const leafId of dir.leafNodeIds) {
      const node = nodeMap.get(leafId)
      if (node) visibleNodes.push(node)
    }
  }

  walk(dirTree, 0)

  const allNodes = [...visibleNodes, ...groupNodes]
  const nodeToDir = new Map<string, string>()
  for (const node of data.nodes) {
    const path = node.source_file || node.entity_file || ''
    nodeToDir.set(node.id, extractDirPath(path))
  }

  const dirToVisibleId = new Map<string, string>()
  for (const groupNode of groupNodes) {
    if (groupNode.dirPath) {
      dirToVisibleId.set(groupNode.dirPath, groupNode.id)
    }
  }
  for (const visibleNode of visibleNodes) {
    dirToVisibleId.set(visibleNode.id, visibleNode.id)
  }

  const edges = aggregateEdges(data.edges, nodeToDir, dirToVisibleId, expanded, dirTree)
  return { nodes: allNodes, edges }
}

function aggregateEdges(
  edges: GraphEdge[],
  nodeToDir: Map<string, string>,
  dirToVisibleId: Map<string, string>,
  expanded: Set<string>,
  dirTree: DirNode,
): AggregatedEdge[] {
  void expanded
  void dirTree
  const pairMap = new Map<string, AggregatedEdge>()

  for (const edge of edges) {
    const srcVisible = resolveToVisible(edge.source, nodeToDir, dirToVisibleId)
    const tgtVisible = resolveToVisible(edge.target, nodeToDir, dirToVisibleId)
    if (!srcVisible || !tgtVisible || srcVisible === tgtVisible) continue

    const key = srcVisible < tgtVisible
      ? `${srcVisible}::${tgtVisible}`
      : `${tgtVisible}::${srcVisible}`

    const existing = pairMap.get(key)
    if (existing) {
      existing.count += 1
    } else {
      pairMap.set(key, {
        source: srcVisible,
        target: tgtVisible,
        count: 1,
        label: edge.label || 'related_to',
      })
    }
  }

  return [...pairMap.values()]
}

function resolveToVisible(
  nodeId: string,
  nodeToDir: Map<string, string>,
  dirToVisibleId: Map<string, string>,
): string | null {
  if (dirToVisibleId.has(nodeId)) {
    return dirToVisibleId.get(nodeId) ?? null
  }

  const dirPath = nodeToDir.get(nodeId) || ''
  if (!dirPath) {
    if (dirToVisibleId.has('(global)')) {
      return dirToVisibleId.get('(global)') ?? null
    }
    return null
  }

  const segments = dirPath.split('/')
  for (let index = segments.length; index >= 1; index -= 1) {
    const ancestorPath = segments.slice(0, index).join('/')
    if (dirToVisibleId.has(ancestorPath)) {
      return dirToVisibleId.get(ancestorPath) ?? null
    }
  }

  return null
}

export function computeBreadcrumb(expanded: Set<string>): string[] {
  if (expanded.size === 0) return []
  let deepest = ''
  for (const path of expanded) {
    if (path.length > deepest.length) deepest = path
  }
  const segments = deepest.split('/')
  const result: string[] = []
  for (let index = 1; index <= segments.length; index += 1) {
    result.push(segments.slice(0, index).join('/'))
  }
  return result
}

export function collapseTo(expanded: Set<string>, targetPath: string): Set<string> {
  const next = new Set<string>()
  for (const path of expanded) {
    if (targetPath.startsWith(path) && path !== targetPath) {
      next.add(path)
    }
  }
  return next
}

export function expandAll(dirTree: DirNode): Set<string> {
  const result = new Set<string>()
  function walk(node: DirNode) {
    if (node.id) result.add(node.id)
    for (const child of node.children) walk(child)
  }
  for (const child of dirTree.children) walk(child)
  return result
}
