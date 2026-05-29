# Flamme Web/PWA 实施计划 — Milestone 1 (Web Skeleton) + Milestone 2 (Graph View + Import Flow)

> 日期：2026年5月23日
> 前置：后端 FastAPI 已运行于 `http://localhost:8765`，CORS 已开启

---

## Task 1: Vite + Svelte 5 项目脚手架

### 步骤

- [ ] **1.1** 创建 `web/` 目录并初始化项目

```bash
cd D:\dev\LLM-WIKI\3.0
mkdir web
cd web
npm init -y
```

- [ ] **1.2** 安装依赖

```bash
npm install -D svelte@5 @sveltejs/vite-plugin-svelte vite typescript
npm install -D @types/d3-force @types/d3-zoom @types/d3-selection
npm install d3-force d3-zoom d3-selection marked katex lucide-svelte
```

- [ ] **1.3** 创建 `web/vite.config.ts`

```ts
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **1.4** 创建 `web/svelte.config.js`

```js
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
export default { preprocess: vitePreprocess() };
```

- [ ] **1.5** 创建 `web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": []
  },
  "include": ["src/**/*.ts", "src/**/*.svelte"],
  "exclude": ["node_modules"]
}
```

- [ ] **1.6** 创建 `web/index.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <meta name="theme-color" content="#FAFAFA" />
  <title>Flamme</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

- [ ] **1.7** 更新 `web/package.json` scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

- [ ] **1.8** 创建目录结构

```bash
mkdir -p src/lib src/api src/stores src/views src/components/graph src/components/import src/components/flame src/components/chat
```

- [ ] **1.9** 验证：`npm run dev` 能启动，浏览器打开 `http://localhost:5173` 无报错

- [ ] **1.10** 提交

```
feat(web): scaffold Vite + Svelte 5 project
```

---

## Task 2: Types 和 API Client

### 步骤

- [ ] **2.1** 创建 `web/src/lib/types.ts` — 从 `plugin/src/types.ts` 提取，去掉 Obsidian 特有字段

```ts
/** Flamme Web — shared types */

export interface ToolStatus {
  name: string;
  label: string;
  status: 'running' | 'progress' | 'done';
  estimate?: string;
  elapsed?: number;
  message?: string;
  files?: string[];
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  toolStatus?: ToolStatus[];
  duration?: number;
  tokenCount?: number;
  suggestedQuestions?: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  level?: string;
  community?: number;
  val?: number;           // degree, used for node radius
  source_file?: string;
  tags?: string[];
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
  count?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface StatusResponse {
  total_documents: number;
  by_level: Record<string, number>;
  total_tags: number;
  embeddings: { embedded: number; total: number };
  last_updated: string | null;
}
```

- [ ] **2.2** 创建 `web/src/api/client.ts` — REST 客户端

```ts
import type { GraphData, StatusResponse } from '$lib/types';

const BASE = '/api';   // vite proxy handles /api → localhost:8765

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

export async function getFullGraph(): Promise<GraphData> {
  return request<GraphData>('/graph/full');
}

export async function ingestFile(path: string, level = 'lite'): Promise<{ status: string }> {
  return request('/ingest', {
    method: 'POST',
    body: JSON.stringify({ path, level }),
  });
}

export async function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>('/status');
}
```

- [ ] **2.3** 创建 `web/src/api/sse.ts` — 从 `plugin/src/api/sse.ts` 复制，去掉 Obsidian 参数

```ts
/** SSE streaming chat — async generator from backend */

export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
  mode: string = 'search',
  selectedFiles?: string[],
): AsyncGenerator<{ type: string; content?: string; questions?: string[] }> {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      mode,
      selected_files: selectedFiles,
    }),
    signal,
  });

  if (!resp.ok || !resp.body) throw new Error('Chat stream failed');

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(line.slice(6));
        yield event;
        if (event.type === 'done' || event.type === 'error') return;
      } catch {
        /* skip malformed */
      }
    }
  }
}
```

- [ ] **2.4** 验证：`npm run build` 无类型错误

- [ ] **2.5** 提交

```
feat(web): add types, REST client, and SSE stream
```

---

## Task 3: App Shell + Tab 导航

### 步骤

- [ ] **3.1** 创建 `web/src/main.ts`

```ts
import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

const app = mount(App, { target: document.getElementById('app')! });

export default app;
```

- [ ] **3.2** 创建 `web/src/app.css` — Apple 风格全局样式

```css
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #FAFAFA;
  --surface: #FFFFFF;
  --text: #1D1D1F;
  --text-secondary: #86868B;
  --border: #E5E5EA;
  --accent: #FF6B35;
  --accent-light: rgba(255, 107, 53, 0.1);
  --radius: 12px;
  --radius-lg: 16px;
  --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --tab-height: 56px;
  --safe-bottom: env(safe-area-inset-bottom, 0px);
}

html, body {
  height: 100%;
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow: hidden;
}

#app {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ── Tab Bar ── */
.tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(var(--tab-height) + var(--safe-bottom));
  padding-bottom: var(--safe-bottom);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 0.5px solid var(--border);
  display: flex;
  justify-content: space-around;
  align-items: center;
  z-index: 100;
}

.tab-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 500;
  padding: 4px 0;
  transition: color 0.2s;
  -webkit-tap-highlight-color: transparent;
}

.tab-item.active {
  color: var(--accent);
}

.tab-item svg {
  width: 24px;
  height: 24px;
}

/* ── Content Area ── */
.view-container {
  flex: 1;
  overflow: hidden;
  padding-bottom: calc(var(--tab-height) + var(--safe-bottom));
}

/* ── Utility ── */
.card {
  background: var(--surface);
  border-radius: var(--radius);
  border: 0.5px solid var(--border);
}

/* KaTeX math */
.flamme-math-block { margin: 12px 0; overflow-x: auto; }
.flamme-math-inline { }
.flamme-wikilink {
  color: var(--accent);
  cursor: pointer;
  border-bottom: 1px dashed var(--accent);
}
```

- [ ] **3.3** 创建 `web/src/App.svelte` — 三 tab 导航

```svelte
<script lang="ts">
  import { Globe, Calendar, MessageCircle } from 'lucide-svelte';
  import GraphView from './views/GraphView.svelte';

  type Tab = 'graph' | 'activity' | 'chat';
  let current: Tab = $state('graph');
</script>

<div class="view-container">
  {#if current === 'graph'}
    <GraphView />
  {:else if current === 'activity'}
    <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-secondary)">
      活跃视图 — 即将推出
    </div>
  {:else}
    <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-secondary)">
      对话视图 — 即将推出
    </div>
  {/if}
</div>

<nav class="tab-bar">
  <button class="tab-item" class:active={current === 'graph'} onclick={() => current = 'graph'}>
    <Globe size={24} />
    <span>图谱</span>
  </button>
  <button class="tab-item" class:active={current === 'activity'} onclick={() => current = 'activity'}>
    <Calendar size={24} />
    <span>活跃</span>
  </button>
  <button class="tab-item" class:active={current === 'chat'} onclick={() => current = 'chat'}>
    <MessageCircle size={24} />
    <span>对话</span>
  </button>
</nav>
```

- [ ] **3.4** 验证：`npm run dev` → 浏览器看到底部 tab 栏，三个 tab 可切换

- [ ] **3.5** 提交

```
feat(web): app shell with 3-tab navigation
```

---

## Task 4: Markdown 渲染库

### 步骤

- [ ] **4.1** 创建 `web/src/lib/markdown.ts` — 从 `plugin/src/lib/markdown.ts` 适配

与 plugin 版本的区别：
- KaTeX 改用 ES import（`import katex from 'katex'`）而非 `require()`
- 去掉 Obsidian 特有的 wikilink 点击处理（保留 HTML span 标记）

```ts
/** Markdown + KaTeX + wikilink rendering */
import { Marked } from 'marked';
import katex from 'katex';

const marked = new Marked({ gfm: true, breaks: true });

export function extractSuggestionQuestions(text: string): { questions: string[]; cleanText: string } {
  const match = text.match(/(?:^|\n)\s*(?:\*\*)?(?:__)?SUGGESTIONS(?:__)?(?:\*\*)?\s*[:：]\s*(\[[\s\S]*?\])\s*$/i);
  if (!match) return { questions: [], cleanText: text };

  try {
    const normalized = match[1].replace(/["\u201C\u201D]/g, '"').replace(/['\u2018\u2019]/g, "'");
    const parsed = JSON.parse(normalized);
    if (Array.isArray(parsed)) {
      const questions = parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
      if (questions.length > 0) {
        return { questions, cleanText: text.slice(0, match.index).trim() };
      }
    }
  } catch { /* keep original text */ }

  return { questions: [], cleanText: text };
}

/** Preprocess [[wikilink]] → clickable HTML spans (no Obsidian handler) */
export function preprocessWikilinks(text: string): string {
  return text.replace(
    /\[\[([^\]]+)\]\]/g,
    '<span class="flamme-wikilink" data-target="$1">$1</span>',
  );
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderKaTeX(math: string, displayMode: boolean): string {
  try {
    return katex.renderToString(math, { displayMode, throwOnError: false });
  } catch {
    return `<code>${escapeHtml(math)}</code>`;
  }
}

/** Render message content: markdown + math + wikilinks */
export function renderMarkdown(text: string): string {
  if (!text) return '';

  const { cleanText } = extractSuggestionQuestions(text);
  const withWikilinks = preprocessWikilinks(cleanText);

  // Protect code blocks
  const codeBlocks: string[] = [];
  let protectedText = withWikilinks;

  protectedText = protectedText.replace(/```[\s\S]*?```/g, (match) => {
    const idx = codeBlocks.length;
    codeBlocks.push(match);
    return `\x00CODEBLOCK${idx}\x00`;
  });

  protectedText = protectedText.replace(/`([^`\n]+)`/g, (match) => {
    const idx = codeBlocks.length;
    codeBlocks.push(match);
    return `\x00CODEBLOCK${idx}\x00`;
  });

  // Block math $$...$$
  protectedText = protectedText.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    try {
      return `<div class="flamme-math-block">${renderKaTeX(math.trim(), true)}</div>`;
    } catch {
      return `<code class="math-error">${escapeHtml(math.trim())}</code>`;
    }
  });

  // Inline math $...$
  protectedText = protectedText.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    try {
      return `<span class="flamme-math-inline">${renderKaTeX(math.trim(), false)}</span>`;
    } catch {
      return `<code class="math-error">${escapeHtml(math.trim())}</code>`;
    }
  });

  // Restore code blocks
  protectedText = protectedText.replace(/\x00CODEBLOCK(\d+)\x00/g, (_, idx) => {
    return codeBlocks[parseInt(idx)];
  });

  return marked.parse(protectedText) as string;
}
```

- [ ] **4.2** 在 `web/src/app.css` 中添加 KaTeX CSS 导入确认（如使用 CDN 可跳过，否则安装 `katex` 的 CSS）

在 `index.html` 的 `<head>` 中添加：
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" />
```

- [ ] **4.3** 验证：在任一 svelte 组件中 import `{ renderMarkdown }` 无报错

- [ ] **4.4** 提交

```
feat(web): markdown + KaTeX + wikilink rendering
```

---

## Task 5: Graph View + D3 Force Layout

### 步骤

- [ ] **5.1** 创建 `web/src/stores/graph.ts` — 图谱数据 store

```ts
import { writable, derived } from 'svelte/store';
import type { GraphData, GraphNode, GraphEdge } from '$lib/types';
import { getFullGraph } from '$api/client';

export const graphData = writable<GraphData>({ nodes: [], edges: [] });
export const selectedNode = writable<GraphNode | null>(null);
export const isLoading = writable(true);
export const isEmpty = derived(graphData, ($d) => $d.nodes.length === 0);

export async function refreshGraph() {
  isLoading.set(true);
  try {
    const data = await getFullGraph();
    graphData.set(data);
  } catch (e) {
    console.error('Failed to load graph:', e);
  } finally {
    isLoading.set(false);
  }
}
```

- [ ] **5.2** 创建 `web/src/components/graph/ForceGraph.svelte` — D3 force simulation

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { GraphNode, GraphEdge } from '$lib/types';

  let {
    nodes = $bindable([]),
    edges = $bindable([]),
    onnodeclick,
    onnodedblclick,
  }: {
    nodes: GraphNode[];
    edges: GraphEdge[];
    onnodeclick?: (node: GraphNode) => void;
    onnodedblclick?: (node: GraphNode) => void;
  } = $props();

  let svgEl: SVGSVGElement;
  let width = $state(0);
  let height = $state(0);
  let simulation: any;

  // Svelte 5 reactive node maps for rendering
  let nodePositions = $state<Map<string, { x: number; y: number }>>(new Map());

  function radius(val?: number): number {
    return Math.max(4, Math.min(20, (val || 1) * 2));
  }

  function ticked(sim: any) {
    const map = new Map<string, { x: number; y: number }>();
    for (const n of sim.nodes()) {
      map.set(n.id, { x: n.x, y: n.y });
    }
    nodePositions = map;
  }

  function buildSimulation() {
    if (simulation) simulation.stop();

    const simNodes = nodes.map((n) => ({ ...n }));
    const nodeById = new Map(simNodes.map((n) => [n.id, n]));
    const simLinks = edges
      .map((e) => ({
        source: nodeById.get(typeof e.source === 'string' ? e.source : (e.source as any).id || e.source) || e.source,
        target: nodeById.get(typeof e.target === 'string' ? e.target : (e.target as any).id || e.target) || e.target,
        label: e.label,
      }))
      .filter((l) => l.source && l.target);

    // @ts-ignore — d3-force types are loose with source/target
    const d3 = await import('d3-force');
    const d3Zoom = await import('d3-zoom');
    const d3Sel = await import('d3-selection');

    simulation = d3.forceSimulation(simNodes)
      .force('link', d3.forceLink(simLinks).id((d: any) => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius((d: any) => radius(d.val) + 4))
      .on('tick', () => ticked(simulation));

    // Zoom
    const svg = d3Sel.select(svgEl);
    const g = svg.select<SVGGElement>('g.graph-container');
    const zoom = d3Zoom.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);
  }

  $effect(() => {
    if (nodes.length > 0 && svgEl) {
      buildSimulation();
    }
  });

  onMount(() => {
    const rect = svgEl.parentElement?.getBoundingClientRect();
    if (rect) {
      width = rect.width;
      height = rect.height;
    }
  });

  onDestroy(() => {
    if (simulation) simulation.stop();
  });
</script>

<div style="width:100%;height:100%;position:relative;">
  <svg bind:this={svgEl} viewBox="0 0 {width} {height}" style="width:100%;height:100%;">
    <g class="graph-container">
      <!-- Edges -->
      {#each edges as edge}
        {@const src = nodePositions.get(typeof edge.source === 'string' ? edge.source : (edge.source as any)?.id)}
        {@const tgt = nodePositions.get(typeof edge.target === 'string' ? edge.target : (edge.target as any)?.id)}
        {#if src && tgt}
          <line
            x1={src.x} y1={src.y}
            x2={tgt.x} y2={tgt.y}
            stroke="#D1D1D6"
            stroke-width="1"
            stroke-opacity="0.6"
          />
        {/if}
      {/each}

      <!-- Nodes -->
      {#each nodes as node}
        {@const pos = nodePositions.get(node.id)}
        {#if pos}
          <g transform="translate({pos.x},{pos.y})">
            <circle
              r={radius(node.val)}
              fill={node.type === 'document' ? '#FF6B35' : '#3A7AB0'}
              stroke="#fff"
              stroke-width="1.5"
              style="cursor:pointer; transition: r 0.2s;"
              onclick={() => onnodeclick?.(node)}
              ondblclick={() => onnodedblclick?.(node)}
            />
            <text
              text-anchor="middle"
              dy={radius(node.val) + 14}
              fill="#1D1D1F"
              font-size="11"
              font-weight="500"
              style="pointer-events:none;"
            >
              {node.label.length > 12 ? node.label.slice(0, 12) + '...' : node.label}
            </text>
          </g>
        {/if}
      {/each}
    </g>
  </svg>
</div>
```

**注意**：上面的 `buildSimulation` 中使用了顶层 `await import()`，这在 Svelte 5 的 `$effect` 中不能直接使用。实际实现需将 d3 的 import 提到模块顶层。修正版：

```svelte
<script context="module" lang="ts">
  // 顶层静态 import，避免 async 问题
  import {
    forceSimulation, forceLink, forceManyBody,
    forceCenter, forceCollide,
  } from 'd3-force';
  import { zoom } from 'd3-zoom';
  import { select } from 'd3-selection';
</script>
```

完整修正后的 `buildSimulation`（无 async）：

```ts
function buildSimulation() {
  if (simulation) simulation.stop();

  const simNodes = nodes.map((n) => ({ ...n, x: width / 2 + Math.random() * 10, y: height / 2 + Math.random() * 10 }));
  const nodeById = new Map(simNodes.map((n) => [n.id, n]));
  const simLinks = edges
    .map((e) => {
      const srcId = typeof e.source === 'string' ? e.source : (e.source as any)?.id;
      const tgtId = typeof e.target === 'string' ? e.target : (e.target as any)?.id;
      const src = nodeById.get(srcId);
      const tgt = nodeById.get(tgtId);
      if (!src || !tgt) return null;
      return { source: src, target: tgt, label: e.label };
    })
    .filter(Boolean) as { source: any; target: any; label: string }[];

  simulation = forceSimulation(simNodes)
    .force('link', forceLink(simLinks).id((d: any) => d.id).distance(80))
    .force('charge', forceManyBody().strength(-120))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collide', forceCollide().radius((d: any) => radius(d.val) + 4))
    .on('tick', () => ticked(simulation));

  // Zoom
  const svg = select(svgEl);
  const g = svg.select<SVGGElement>('g.graph-container');
  const zoomBehavior = zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => g.attr('transform', event.transform));
  svg.call(zoomBehavior);
}
```

- [ ] **5.3** 创建 `web/src/views/GraphView.svelte` — 图谱页面编排

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { graphData, isLoading, isEmpty, selectedNode, refreshGraph } from '../stores/graph';
  import ForceGraph from '../components/graph/ForceGraph.svelte';
  import DropZone from '../components/import/DropZone.svelte';

  onMount(() => {
    refreshGraph();
  });

  function handleNodeClick(node: any) {
    selectedNode.set(node);
  }

  function handleNodeDblClick(node: any) {
    // Milestone 3: 打开对话视图并绑定节点
    console.log('Double-clicked:', node);
  }
</script>

<div class="graph-page" style="width:100%;height:100%;position:relative;">
  {#if $isLoading}
    <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-secondary)">
      加载中...
    </div>
  {:else if $isEmpty}
    <DropZone />
  {:else}
    <ForceGraph
      nodes={$graphData.nodes}
      edges={$graphData.edges}
      onnodeclick={handleNodeClick}
      onnodedblclick={handleNodeDblClick}
    />
    <!-- 右下角 [+] 按钮，可再次导入 -->
    <DropZone mode="button" />
  {/if}
</div>
```

- [ ] **5.4** 验证：
  1. 后端运行（`python -m src.api.app`）
  2. 后端有数据（已 ingest 过文件）
  3. `npm run dev` → 图谱页显示节点和边
  4. 可以拖拽、缩放

- [ ] **5.5** 提交

```
feat(web): D3 force graph view with zoom/pan
```

---

## Task 6: Import Flow (DropZone)

### 步骤

- [ ] **6.1** 创建 `web/src/components/import/DropZone.svelte`

支持两种模式：
- `mode="full"` — 居中全屏拖拽区（空状态时）
- `mode="button"` — 右下角 FAB 按钮（有数据时）

```svelte
<script lang="ts">
  import { refreshGraph } from '../../stores/graph';
  import { ingestFile } from '../../api/client';
  import { Plus, Upload, FileText, Loader2 } from 'lucide-svelte';

  let {
    mode = 'full',
  }: {
    mode?: 'full' | 'button';
  } = $props();

  let isDragging = $state(false);
  let isProcessing = $state(false);
  let statusText = $state('');
  let files: File[] = $state([]);

  const ACCEPTED = ['.pdf', '.md', '.pptx', '.txt'];

  function isAccepted(name: string): boolean {
    return ACCEPTED.some((ext) => name.toLowerCase().endsWith(ext));
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    isDragging = false;
    const dropped = Array.from(e.dataTransfer?.files || []);
    const valid = dropped.filter((f) => isAccepted(f.name));
    if (valid.length === 0) return;
    processFiles(valid);
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    const selected = Array.from(input.files || []);
    if (selected.length === 0) return;
    processFiles(selected);
    input.value = ''; // reset
  }

  async function processFiles(fileList: File[]) {
    isProcessing = true;
    statusText = '正在解析...';

    for (let i = 0; i < fileList.length; i++) {
      const f = fileList[i];
      statusText = `正在处理 ${f.name} (${i + 1}/${fileList.length})`;

      // 后端 ingest 接受 path（vault 中的路径），
      // Web 端需要先把文件上传到后端 vault 目录。
      // 当前方案：POST 文件到 /api/ingest，后端接收 file 并写入 vault。
      // TODO: 后端需要新增文件上传端点（multipart/form-data）
      // 临时方案：使用文件名调用 ingestFile
      try {
        await ingestFile(f.name);
      } catch (e) {
        console.error(`Failed to ingest ${f.name}:`, e);
      }
    }

    statusText = '正在更新图谱...';
    await refreshGraph();
    statusText = '';
    isProcessing = false;
  }

  function openFileDialog() {
    document.getElementById('dropzone-file-input')?.click();
  }
</script>

{#if mode === 'button'}
  <!-- FAB button -->
  <button
    class="fab"
    onclick={openFileDialog}
    title="导入文件"
    style="position:fixed;bottom:calc(var(--tab-height) + var(--safe-bottom) + 16px);right:16px;width:48px;height:48px;border-radius:50%;background:var(--accent);color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 12px rgba(255,107,53,0.3);z-index:50;"
  >
    {#if isProcessing}
      <Loader2 size={22} style="animation:spin 1s linear infinite;" />
    {:else}
      <Plus size={22} />
    {/if}
  </button>
  <input
    id="dropzone-file-input"
    type="file"
    accept=".pdf,.md,.pptx,.txt"
    multiple
    onchange={handleFileInput}
    style="display:none;"
  />
{:else}
  <!-- Full-screen drop zone -->
  <div
    class="dropzone"
    role="button"
    tabindex="0"
    style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:16px;color:var(--text-secondary);"
    ondragover={(e) => { e.preventDefault(); isDragging = true; }}
    ondragleave={() => isDragging = false}
    ondrop={handleDrop}
    onclick={openFileDialog}
    onkeydown={(e) => e.key === 'Enter' && openFileDialog()}
    class:dragging={isDragging}
  >
    {#if isProcessing}
      <Loader2 size={48} style="animation:spin 1s linear infinite;color:var(--accent);" />
      <p style="font-size:15px;font-weight:500;">{statusText}</p>
    {:else}
      <Upload size={48} />
      <p style="font-size:17px;font-weight:600;color:var(--text);">拖入你的第一份资料</p>
      <p style="font-size:13px;">支持 PDF、Markdown、PPTX</p>
    {/if}
    <input
      id="dropzone-file-input"
      type="file"
      accept=".pdf,.md,.pptx,.txt"
      multiple
      onchange={handleFileInput}
      style="display:none;"
    />
  </div>
{/if}

<style>
  .dropzone.dragging {
    background: var(--accent-light);
    border: 2px dashed var(--accent);
    border-radius: var(--radius-lg);
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
```

- [ ] **6.2** 后端文件上传端点（如果尚未存在）

当前后端 `POST /api/ingest` 接受 `{ path: string }` — 指的是 vault 中的路径。Web 端需要新增一个 multipart 上传端点。

在 `src/api/routes/ingest.py` 中新增：

```python
@router.post("/upload")
async def upload_file(request: Request, file: UploadFile):
    """接收 Web 端上传的文件，保存到 vault，然后触发 ingest"""
    from fastapi import UploadFile
    import shutil, os

    cfg = get_request_config_or_default(request)
    save_path = os.path.join(cfg.vault_path, file.filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 触发 ingest
    # ... (同 ingest_file 逻辑，传入 save_path)
    return {"status": "ok", "path": save_path}
```

Web 端 `client.ts` 中新增：

```ts
export async function uploadAndIngest(file: File): Promise<{ status: string }> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch('/api/ingest/upload', { method: 'POST', body: form });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.json();
}
```

- [ ] **6.3** 更新 DropZone 使用 `uploadAndIngest` 替代 `ingestFile`

将 `processFiles` 中的 `await ingestFile(f.name)` 改为：

```ts
import { uploadAndIngest } from '../../api/client';
// ...
await uploadAndIngest(f);
```

- [ ] **6.4** 验证：
  1. 空状态显示 DropZone
  2. 拖入 PDF → 显示处理动画 → 完成后图谱出现新节点
  3. 有数据时右下角 [+] 按钮可再次导入

- [ ] **6.5** 提交

```
feat(web): file drop zone with upload + ingest flow
```

---

## Task 7: 像素火苗组件

### 步骤

- [ ] **7.1** 创建 `web/src/components/flame/PixelFlame.svelte` — 从 `FlameAvatar.svelte` 适配

与 plugin 版本的区别：
- 去掉 Obsidian `onMount`/`onDestroy` 的特殊处理（Svelte 5 web 原生即可）
- `require('katex')` 不存在于此组件，无需改动
- 添加 `size` prop 控制 canvas 显示大小
- 支持 `idle` | `active` | `pulse` 三种模式

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let {
    mode = 'idle',
    size = 120,
  }: {
    /** idle: 空状态居中轻柔跳动 | active: 导入处理中 | pulse: 导航栏 logo 静态微闪 */
    mode?: 'idle' | 'active' | 'pulse';
    size?: number;
  } = $props();

  // 将 mode 映射到原始状态
  const modeToState: Record<string, string> = {
    idle: 'peek',
    active: 'think',
    pulse: 'peek',
  };

  let state = $derived(modeToState[mode] || 'peek');

  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null;
  let animationFrameId: number;
  let startTime: number | null = null;

  // ═══════════════════════════════════════════
  // COLORS
  // ═══════════════════════════════════════════
  const FC = {
    red:   { outer:'#8B1A10', mid:'#C04A28', core:'#F5C5A0', hi:'#FDE8D8', spark:'#C04A28', dot:'#EEDDD8' },
    blue:  { outer:'#1A3A5C', mid:'#3A7AB0', core:'#A8CCE8', hi:'#D8E8F5', spark:'#3A7AB0', dot:'#D8E0EE' },
    green: { outer:'#194F1B', mid:'#3BA34F', core:'#B3D8A7', hi:'#D0E9DD', spark:'#3BA34F', dot:'#E6EEE2' },
    pink:  { outer:'#8B2050', mid:'#C04A78', core:'#F5C5D8', hi:'#FDE8F0', spark:'#C04A78', dot:'#EED8E2' },
  };
  const STATE_COLOR: Record<string, keyof typeof FC> = {
    peek:'red', look:'green', think:'blue', happy:'pink', answer:'red', confused:'blue'
  };

  // ═══════════════════════════════════════════
  // GRID
  // ═══════════════════════════════════════════
  const PX = 20;
  const CANVAS_SIZE = 720;

  function px(x: number, y: number, c?: string) {
    if (c && ctx) {
      ctx.fillStyle = c;
      ctx.fillRect(Math.round(x) * PX, Math.round(y) * PX, PX, PX);
    }
  }

  function fillRect(x: number, y: number, w: number, h: number, c: string) {
    for (let dy = 0; dy < h; dy++)
      for (let dx = 0; dx < w; dx++)
        px(x + dx, y + dy, c);
  }

  function drawBg() {
    if (ctx) ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
  }

  // ═══════════════════════════════════════════
  // FLAME CHARACTER (identical to plugin)
  // ═══════════════════════════════════════════
  const FX = 18, FY = 18;

  const SLICES = {
    outer: [[-12,1],[-11,2],[-10,3],[-9,5],[-8,6],[-7,7],[-6,7],[-5,8],[-4,8],[-3,8],[-2,8],[-1,8],[0,8],[1,8],[2,7],[3,7],[4,6],[5,5],[6,5]],
    mid:   [[-9,1],[-8,3],[-7,5],[-6,5],[-5,6],[-4,6],[-3,6],[-2,6],[-1,6],[0,6],[1,6],[2,5],[3,5],[4,3]],
    core:  [[-6,1],[-5,3],[-4,4],[-3,5],[-2,5],[-1,5],[0,5],[1,4],[2,3],[3,2]],
    hi:    [[-4,2],[-3,3],[-2,3],[-1,2]]
  } as const;

  function drawFlameBody(cx: number, cy: number, C: any, flicker: number) {
    for (const key of ['outer','mid','core','hi'] as const) {
      const color = C[key];
      for (const [dy, hw] of SLICES[key]) {
        const fw = Math.round(Math.sin(flicker*0.08 + dy*0.4)*0.6);
        for (let x = -(hw+fw); x <= (hw+fw); x++) px(cx+x, cy+dy, color);
        if (key === 'outer' && hw > 1) {
          const topBoost = dy < -6 ? 0.3 : 0;
          if (Math.sin(dy*2.7+flicker*0.05)>-topBoost) px(cx-hw-fw-1, cy+dy, color);
          if (Math.sin(dy*1.9+flicker*0.07+1)>-topBoost) px(cx+hw+fw+1, cy+dy, color);
          if (dy < -8 && Math.sin(dy*3.5+flicker*0.06)>-0.2) {
            px(cx-hw-fw-2, cy+dy, color);
            px(cx+hw+fw+2, cy+dy, color);
          }
        }
      }
    }
  }

  function drawTip(tx: number, ty: number, h: number, c1: string, c2: string, c3?: string) {
    for (let i = 0; i < h; i++) {
      const w = Math.max(0, Math.floor((h - i) * 0.55));
      for (let j = -w; j <= w; j++) {
        const c = i === 0 ? c1 : (i < h*0.3 ? (c3 || c2) : c2);
        px(tx + j, ty - i, c);
      }
    }
  }

  function drawFlameTips(cx: number, cy: number, C: any, flicker: number) {
    const sw1 = Math.sin(flicker*0.13), sw2 = Math.sin(flicker*0.17+1.5);
    const sw3 = Math.sin(flicker*0.11+3.0), sw4 = Math.sin(flicker*0.09+4.0);
    const h1 = 3+Math.round(Math.abs(Math.sin(flicker*0.09))*2);
    const h2 = 5+Math.round(Math.abs(Math.sin(flicker*0.07))*2);
    const h3 = 3+Math.round(Math.abs(Math.sin(flicker*0.1+2))*2);
    const h4 = 2+Math.round(Math.abs(Math.sin(flicker*0.12+1))*2);
    drawTip(cx-4+Math.round(sw1*1), cy-11, h1, C.outer, C.mid);
    drawTip(cx+Math.round(sw2*0.5), cy-12, h2, C.outer, C.mid, C.core);
    drawTip(cx+4+Math.round(sw3*-1), cy-10, h3, C.outer, C.mid);
    drawTip(cx-2+Math.round(sw4*0.5), cy-13, h4, C.outer, C.mid);
  }

  function drawEmbers(cx: number, cy: number, C: any, f: number) {
    if (!ctx) return;
    const positions = [
      {ox:-10,oy:-9,ph:0},{ox:10,oy:-6,ph:1.5},{ox:-7,oy:-13,ph:3},{ox:9,oy:-11,ph:4.5},
      {ox:-11,oy:-4,ph:2.5},{ox:11,oy:-9,ph:5.0}
    ];
    for (const e of positions) {
      const vis = Math.sin(f*0.06+e.ph);
      if (vis > 0) {
        const yoff = Math.round(Math.sin(f*0.04+e.ph)*2);
        ctx.globalAlpha = vis * 0.7;
        px(cx+e.ox, cy+e.oy+yoff, C.outer);
        px(cx+e.ox, cy+e.oy+yoff-1, C.mid);
        ctx.globalAlpha = 1;
      }
    }
  }

  function drawLog(cx: number, by: number) {
    fillRect(cx-9,by,19,3,'#654321');
    fillRect(cx-8,by,17,1,'#7A5A35');
    fillRect(cx-7,by+1,15,1,'#6B4E2F');
    px(cx-5,by+2,'#3A2510'); px(cx-1,by+2,'#3A2510');
    px(cx+4,by+2,'#3A2510'); px(cx+1,by+1,'#3A2510');
    px(cx-10,by,'#7A5A35'); px(cx-10,by+1,'#654321'); px(cx-10,by+2,'#543219');
    px(cx+10,by,'#7A5A35'); px(cx+10,by+1,'#654321'); px(cx+10,by+2,'#543219');
  }

  function drawFlameEyes(cx: number, ey: number, type: string) {
    const lx = cx-3, rx = cx+2;
    switch(type) {
      case 'forward':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey+1,'#000'); px(rx+1,ey+1,'#000'); break;
      case 'happy':
        px(lx,ey+1,'#000'); px(lx+1,ey,'#000');
        px(rx,ey,'#000'); px(rx+1,ey+1,'#000'); break;
      case 'up':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey,'#000'); px(rx,ey,'#000'); break;
      case 'blink':
        fillRect(lx,ey+1,2,1,'#000'); fillRect(rx,ey+1,2,1,'#000'); break;
      case 'wide':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey,'#000'); px(rx,ey,'#000'); break;
    }
  }

  function drawFlameMouth(cx: number, my: number, type: string) {
    switch(type) {
      case 'neutral': fillRect(cx-1,my,3,1,'#333'); break;
      case 'smile':
        px(cx-2,my-1,'#333'); fillRect(cx-1,my,3,1,'#333'); px(cx+2,my-1,'#333'); break;
      case 'small': px(cx,my,'#333'); break;
      case 'o':
        fillRect(cx-1,my,3,1,'#333'); px(cx-1,my+1,'#333'); px(cx+1,my+1,'#333'); break;
    }
  }

  function drawFlame(cx: number, cy: number, opts: any = {}) {
    if (!ctx) return;
    const { color='red', eyes='forward', mouth='neutral',
            flicker=0, bounce=0, tilt=0, offsetY=0 } = opts;
    const C = FC[color as keyof typeof FC];
    const y = cy + Math.round(bounce) + Math.round(offsetY);
    const t = Math.round(tilt);
    ctx.globalAlpha = 0.15;
    for (const [dy, hw] of SLICES.outer)
      for (let x = -(hw+3); x <= (hw+3); x++) px(cx+t+x, y+dy, C.hi);
    ctx.globalAlpha = 1;
    drawLog(cx+t, y+6);
    drawFlameTips(cx+t, y, C, flicker);
    drawFlameBody(cx+t, y, C, flicker);
    drawEmbers(cx+t, y, C, flicker);
    drawFlameEyes(cx+t, y-3, eyes);
    drawFlameMouth(cx+t, y+1, mouth);
  }

  // Particles
  let particles: any[] = [];
  function addP(x: number, y: number, c: string) {
    particles.push({ x, y, vx: (Math.random()-.5)*.5, vy: -Math.random()*.5-.2, life: 1, c });
  }
  function tickP() {
    if (!ctx) return;
    for (let i = particles.length-1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx; p.y += p.vy; p.vy += 0.02; p.life -= 0.018;
      if (p.life <= 0) { particles.splice(i, 1); continue; }
      ctx.globalAlpha = Math.min(1, p.life*1.5);
      px(Math.round(p.x), Math.round(p.y), p.c);
      ctx.globalAlpha = 1;
    }
  }

  // Easing
  function easeOut(t: number) { return 1 - Math.pow(1-t, 3); }

  // State renderers — only peek (idle) and think (active) needed for web
  function renderPeek(f: number, t: number, pt: number) {
    const C = FC.red;
    let offsetY = 0, bounce = 0, eyes = 'forward';
    if (pt < 0.45) {
      offsetY = (1 - easeOut(pt / 0.45)) * 24;
    } else if (pt < 0.7) {
      const p = (pt-0.45)/0.25;
      bounce = Math.sin(p*Math.PI*3)*(1-p)*2;
      eyes = p < 0.2 ? 'blink' : p < 0.4 ? 'happy' : 'forward';
    } else {
      bounce = Math.sin(pt*Math.PI*2)*0.3;
    }
    drawFlame(FX, FY, {
      color:'red', eyes, mouth: pt > 0.6 ? 'smile' : 'neutral',
      flicker: f, bounce: Math.round(bounce), offsetY: Math.round(offsetY),
    });
    if (pt < 0.45 && f%4 === 0) addP(FX-3+Math.random()*7, FY+12+Math.round(offsetY), C.spark);
    if (pt > 0.5 && pt < 0.7 && f%5 === 0) addP(FX-5+Math.random()*11, FY-10, C.spark);
    tickP();
  }

  function renderThink(f: number, t: number, pt: number) {
    const C = FC.blue;
    const eyes = Math.sin(f*0.04) > 0.9 ? 'blink' : 'up';
    const tilt = Math.sin(f*0.08) * 0.6;
    drawFlame(FX, FY, { color:'blue', eyes, mouth:'small', flicker:f, tilt: Math.round(tilt*10)/10 });
    if (f%15 < 3 && pt > 0.2) addP(FX-3+Math.random()*7, FY-10, C.spark);
    tickP();
  }

  const RENDERERS: Record<string, (f:number, t:number, pt:number) => void> = {
    peek: renderPeek,
    think: renderThink,
  };

  const FPS = 30;
  const STATE_DUR: Record<string, number> = { peek: 2.5, think: 4 };

  function render(f: number) {
    const dur = STATE_DUR[state] || 3;
    const total = FPS * dur;
    const t = f / total;
    const pt = ((t % 1) + 1) % 1;
    drawBg();
    RENDERERS[state]?.(f, t, pt);
  }

  function loop(ts: number) {
    if (!startTime) startTime = ts;
    const elapsed = (ts - startTime) / 1000;
    const dur = STATE_DUR[state] || 3;
    const loopSec = elapsed % dur;
    const frame = Math.floor(loopSec * FPS);
    if (loopSec < 0.05) particles = [];
    render(frame);
    animationFrameId = requestAnimationFrame(loop);
  }

  $effect(() => {
    // state changed via mode
    particles = [];
  });

  onMount(() => {
    ctx = canvas.getContext('2d');
    animationFrameId = requestAnimationFrame(loop);
  });

  onDestroy(() => {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
  });
</script>

<canvas
  bind:this={canvas}
  width="720"
  height="720"
  style="width: {size}px; height: {size}px; image-rendering: pixelated; image-rendering: crisp-edges;"
></canvas>
```

- [ ] **7.2** 集成 PixelFlame 到三处

**导航栏 Logo** — 在 `App.svelte` 的 tab-bar 上方添加顶部导航：

```svelte
<!-- App.svelte 顶部 -->
<header style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:var(--surface);border-bottom:0.5px solid var(--border);">
  <PixelFlame mode="pulse" size={28} />
  <span style="font-weight:600;font-size:17px;">Flamme</span>
</header>
```

**空状态** — 在 `DropZone.svelte` 的 full mode 中替换 Upload icon：

```svelte
<!-- 替换 <Upload size={48} /> 为 -->
<PixelFlame mode="idle" size={120} />
```

**处理中** — 在 DropZone 的 isProcessing 状态中替换 Loader2：

```svelte
<!-- 替换 <Loader2 size={48} ... /> 为 -->
<PixelFlame mode="active" size={80} />
```

- [ ] **7.3** 在 App.svelte 中 import PixelFlame：

```ts
import PixelFlame from './components/flame/PixelFlame.svelte';
```

在 DropZone.svelte 中：
```ts
import PixelFlame from './flame/PixelFlame.svelte';
```

- [ ] **7.4** 验证：
  1. 空状态：中心 120px 火苗轻柔跳动 + "拖入你的第一份资料"
  2. 拖入文件后：火苗变蓝（think 状态）+ "正在解析..."
  3. 顶部导航栏：28px 火苗 logo + "Flamme" 文字

- [ ] **7.5** 提交

```
feat(web): pixel flame component — logo, processing, empty state
```

---

## 验证清单

完成所有 Task 后，端到端验证：

- [ ] `npm run dev` 启动无错误
- [ ] 浏览器打开 `http://localhost:5173`
- [ ] 空状态：像素火苗 + 拖拽提示
- [ ] 拖入 PDF 文件 → 后端处理 → 图谱节点出现
- [ ] 图谱可拖拽、缩放（鼠标滚轮/触摸双指）
- [ ] 点击节点 → console 输出（Milestone 3 将做侧滑面板）
- [ ] 三 tab 切换正常
- [ ] `npm run build` 无错误
- [ ] 移动端浏览器宽度下 tab 栏和布局正常

---

## 文件结构总览

```
web/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── svelte.config.js
└── src/
    ├── main.ts
    ├── app.css
    ├── App.svelte
    ├── lib/
    │   ├── types.ts
    │   └── markdown.ts
    ├── api/
    │   ├── client.ts
    │   └── sse.ts
    ├── stores/
    │   └── graph.ts
    ├── views/
    │   └── GraphView.svelte
    └── components/
        ├── graph/
        │   └── ForceGraph.svelte
        ├── import/
        │   └── DropZone.svelte
        ├── flame/
        │   └── PixelFlame.svelte
        └── chat/
            (empty — Milestone 3)
```
