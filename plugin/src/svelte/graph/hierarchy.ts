/**
 * hierarchy.ts — 目录树构建 + 分层可见图 + 边聚合
 *
 * 从 GraphData 的 source_file 路径解析目录树，
 * 根据展开状态生成可见节点和聚合边。
 */

import type { GraphData, GraphNode, GraphEdge, DirNode, AggregatedEdge } from '../../types';

// ── 目录树构建 ─────────────────────────────────────────────

/**
 * 从 GraphData 的 source_file 构建 DirNode 树。
 * 每个 source_file 的目录部分成为树的一个节点。
 */
export function buildDirTree(data: GraphData): DirNode {
  const root: DirNode = { id: '', label: 'vault', children: [], leafNodeIds: [], totalCount: 0 };

  for (const node of data.nodes) {
    const path = node.source_file || node.entity_file || '';
    const dirPath = extractDirPath(path);

    // 找到或创建目录链
    const dirNode = ensureDirChain(root, dirPath);
    dirNode.leafNodeIds.push(node.id);
  }

  // 递归计算 totalCount
  computeTotalCount(root);

  return root;
}

function extractDirPath(filePath: string): string {
  if (!filePath) return '(global)';
  const lastSlash = filePath.lastIndexOf('/');
  if (lastSlash <= 0) return '';
  return filePath.substring(0, lastSlash);
}

function ensureDirChain(root: DirNode, dirPath: string): DirNode {
  if (!dirPath || dirPath === '(global)') {
    // 放入虚拟 (global) 分组
    let globalDir = root.children.find(c => c.id === '(global)');
    if (!globalDir) {
      globalDir = { id: '(global)', label: '(global)', children: [], leafNodeIds: [], totalCount: 0 };
      root.children.push(globalDir);
    }
    return globalDir;
  }

  const segments = dirPath.split('/');
  let current = root;

  for (let i = 0; i < segments.length; i++) {
    const segId = segments.slice(0, i + 1).join('/');
    let child = current.children.find(c => c.id === segId);
    if (!child) {
      child = { id: segId, label: segments[i], children: [], leafNodeIds: [], totalCount: 0 };
      current.children.push(child);
    }
    current = child;
  }

  return current;
}

function computeTotalCount(node: DirNode): number {
  let count = node.leafNodeIds.length;
  for (const child of node.children) {
    count += computeTotalCount(child);
  }
  node.totalCount = count;
  return count;
}

// ── 可见图计算 ─────────────────────────────────────────────

/**
 * 根据展开状态，生成当前可见的节点列表和聚合边。
 *
 * 规则：
 * - 根节点的直接子目录总是显示为分组节点
 * - 展开的目录：显示其子目录（分组）和直接叶节点
 * - 折叠的目录：显示为一个分组节点
 */
export function computeVisibleGraph(
  data: GraphData,
  dirTree: DirNode,
  expanded: Set<string>,
): { nodes: GraphNode[], edges: AggregatedEdge[] } {

  const nodeMap = new Map<string, GraphNode>();
  for (const n of data.nodes) {
    nodeMap.set(n.id, n);
  }

  const visibleNodes: GraphNode[] = [];
  const groupNodes: GraphNode[] = [];

  // 遍历树，收集可见节点
  function walk(dir: DirNode, depth: number) {
    if (depth === 0) {
      // 根层：显示一级目录为分组
      for (const child of dir.children) {
        collectVisible(child, 1);
      }
      return;
    }
  }

  function collectVisible(dir: DirNode, depth: number) {
    const isExpanded = expanded.has(dir.id);

    if (!isExpanded) {
      // 折叠 → 显示为分组节点
      groupNodes.push({
        id: 'group::' + dir.id,
        label: dir.label,
        type: 'group',
        isGroup: true,
        childCount: dir.totalCount,
        dirPath: dir.id,
      });
      return;
    }

    // 展开 → 子目录作为分组，直接叶节点作为叶节点
    for (const child of dir.children) {
      collectVisible(child, depth + 1);
    }

    for (const leafId of dir.leafNodeIds) {
      const node = nodeMap.get(leafId);
      if (node) {
        visibleNodes.push(node);
      }
    }
  }

  // 从根开始
  walk(dirTree, 0);

  const allNodes = [...visibleNodes, ...groupNodes];

  // 构建 nodeId → 包含它的目录路径 的映射
  const nodeToDir = new Map<string, string>();
  for (const n of data.nodes) {
    const path = n.source_file || n.entity_file || '';
    nodeToDir.set(n.id, extractDirPath(path));
  }

  // 构建目录路径 → 可见 ID 的映射
  const dirToVisibleId = new Map<string, string>();
  for (const gn of groupNodes) {
    if (gn.dirPath) {
      dirToVisibleId.set(gn.dirPath, gn.id);
    }
  }
  // 展开目录下的叶节点自己就是可见的
  for (const vn of visibleNodes) {
    dirToVisibleId.set(vn.id, vn.id);
  }

  // 聚合边
  const edges = aggregateEdges(
    data.edges,
    nodeToDir,
    dirToVisibleId,
    expanded,
    dirTree,
  );

  return { nodes: allNodes, edges };
}

// ── 边聚合 ─────────────────────────────────────────────────

/**
 * 将原始边按可见实体聚合。
 * - 两个端点都可见 → 直接边
 * - 端点在折叠目录中 → 上溯到最近的可见分组
 * - 同组内部边 → 跳过
 */
function aggregateEdges(
  edges: GraphEdge[],
  nodeToDir: Map<string, string>,
  dirToVisibleId: Map<string, string>,
  expanded: Set<string>,
  dirTree: DirNode,
): AggregatedEdge[] {

  const pairMap = new Map<string, AggregatedEdge>();

  for (const e of edges) {
    const srcVisible = resolveToVisible(e.source, nodeToDir, dirToVisibleId, expanded, dirTree);
    const tgtVisible = resolveToVisible(e.target, nodeToDir, dirToVisibleId, expanded, dirTree);

    if (!srcVisible || !tgtVisible) continue;
    if (srcVisible === tgtVisible) continue; // 同组内部，跳过

    const key = srcVisible < tgtVisible
      ? `${srcVisible}::${tgtVisible}`
      : `${tgtVisible}::${srcVisible}`;

    const existing = pairMap.get(key);
    if (existing) {
      existing.count++;
    } else {
      pairMap.set(key, { source: srcVisible, target: tgtVisible, count: 1, label: e.label || 'related_to' });
    }
  }

  // 修正方向：确保 source < target 保持一致（无向边）
  const result: AggregatedEdge[] = [];
  for (const ae of pairMap.values()) {
    result.push(ae);
  }
  return result;
}

/**
 * 将一个节点解析到当前可见层级的 ID。
 * 如果节点本身可见（叶节点），返回其 id。
 * 如果在折叠目录中，返回最近可见的 group::xxx id。
 */
function resolveToVisible(
  nodeId: string,
  nodeToDir: Map<string, string>,
  dirToVisibleId: Map<string, string>,
  expanded: Set<string>,
  dirTree: DirNode,
): string | null {
  // 直接可见？
  if (dirToVisibleId.has(nodeId)) {
    return dirToVisibleId.get(nodeId)!;
  }

  // 找到这个节点所在的目录
  const dirPath = nodeToDir.get(nodeId) || '';
  if (!dirPath) {
    // 全局 entity → 检查 (global) 分组是否可见
    const globalId = 'group::(global)';
    if (dirToVisibleId.has('(global)')) {
      return dirToVisibleId.get('(global)')!;
    }
    return null;
  }

  // 从节点目录向上走，找到最近的可见祖先
  const segments = dirPath.split('/');
  for (let i = segments.length; i >= 1; i--) {
    const ancestorPath = segments.slice(0, i).join('/');
    if (dirToVisibleId.has(ancestorPath)) {
      return dirToVisibleId.get(ancestorPath)!;
    }
  }

  return null;
}

// ── 面包屑 ─────────────────────────────────────────────────

export function computeBreadcrumb(expanded: Set<string>): string[] {
  if (expanded.size === 0) return [];
  // 找最深展开路径
  let deepest = '';
  for (const p of expanded) {
    if (p.length > deepest.length) deepest = p;
  }
  const segments = deepest.split('/');
  const result: string[] = [];
  for (let i = 1; i <= segments.length; i++) {
    result.push(segments.slice(0, i).join('/'));
  }
  return result;
}

/**
 * 折叠到指定层级：移除所有比 targetPath 更深的展开状态
 */
export function collapseTo(expanded: Set<string>, targetPath: string): Set<string> {
  const next = new Set<string>();
  for (const p of expanded) {
    if (p.length < targetPath.length || p === targetPath) {
      // keep paths shorter than or equal to target
      // but remove the target itself (we're collapsing AT this level)
    }
    // Actually: keep everything that's a prefix of targetPath, excluding targetPath itself
    if (targetPath.startsWith(p) && p !== targetPath) {
      next.add(p);
    }
  }
  return next;
}

/**
 * 展开所有目录
 */
export function expandAll(dirTree: DirNode): Set<string> {
  const result = new Set<string>();
  function walk(node: DirNode) {
    if (node.id) result.add(node.id);
    for (const c of node.children) walk(c);
  }
  for (const c of dirTree.children) walk(c);
  return result;
}
