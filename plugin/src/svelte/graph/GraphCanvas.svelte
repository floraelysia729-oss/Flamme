<script lang="ts">
  import dagre from 'dagre';
  import type { GraphData, GraphNode } from '../../types';

  interface LayoutNode extends GraphNode {
    x: number;
    y: number;
    width: number;
    height: number;
  }
  interface LayoutEdge {
    source: string;
    target: string;
    label: string;
    count: number;
    points: { x: number; y: number }[];
  }

  let {
    key = 0,
    data,
    searchQuery = '',
    onnodeclick,
    onnodedblclick,
  }: {
    key?: number;
    data: GraphData;
    searchQuery?: string;
    onnodeclick?: (node: GraphNode) => void;
    onnodedblclick?: (node: GraphNode) => void;
  } = $props();

  let svgEl: SVGSVGElement | undefined = $state();
  let hoveredId: string | null = $state(null);
  let tx = $state(0);
  let ty = $state(0);
  let sc = $state(1);
  let isPanning = false;
  let panStartX = 0;
  let panStartY = 0;

  const COLORS = [
    '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
    '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
  ];

  // Dagre layout computation
  let layout = $derived.by(() => {
    if (!data.nodes.length) return { nodes: [] as LayoutNode[], edges: [] as LayoutEdge[] };

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70, marginx: 40, marginy: 40 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const n of data.nodes) {
      const label = n.label || n.id;
      if (n.isGroup) {
        // Group nodes: wider, taller
        const w = Math.max(120, Math.min(220, label.length * 12 + 80));
        g.setNode(n.id, { label, width: w, height: 48 });
      } else {
        const w = Math.max(80, Math.min(180, label.length * 9 + 24));
        g.setNode(n.id, { label, width: w, height: 32 });
      }
    }
    for (const e of data.edges) {
      if (g.hasNode(e.source) && g.hasNode(e.target)) {
        g.setEdge(e.source, e.target, {});
      }
    }

    dagre.layout(g);

    const nodes = data.nodes.map((n): LayoutNode => {
      const pos = g.node(n.id);
      return { ...n, x: pos.x, y: pos.y, width: pos.width, height: pos.height };
    });

    const edges = data.edges
      .filter(e => g.hasNode(e.source) && g.hasNode(e.target))
      .map((e): LayoutEdge => {
        const ed = g.edge(e.source, e.target);
        return { source: e.source, target: e.target, label: e.label || '', count: e.count || 1, points: ed.points };
      });

    if (nodes.length > 0) {
      const xs = nodes.map(n => n.x);
      const ys = nodes.map(n => n.y);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      return { nodes, edges, cx, cy };
    }
    return { nodes, edges, cx: 0, cy: 0 };
  });

  // Auto-fit on first render or key change
  let lastKey = -1;
  $effect(() => {
    if (svgEl && layout.nodes.length > 0 && key !== lastKey) {
      lastKey = key;
      const rect = svgEl.getBoundingClientRect();
      const xs = layout.nodes.map(n => n.x);
      const ys = layout.nodes.map(n => n.y);
      const ws = layout.nodes.map(n => n.width);
      const hs = layout.nodes.map(n => n.height);
      const minX = Math.min(...xs) - 80;
      const maxX = Math.max(...xs) + 80;
      const minY = Math.min(...ys) - 60;
      const maxY = Math.max(...ys) + 60;
      const graphW = maxX - minX;
      const graphH = maxY - minY;
      const pad = 0.85;
      const scaleX = (rect.width * pad) / graphW;
      const scaleY = (rect.height * pad) / graphH;
      sc = Math.min(scaleX, scaleY, 2);
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      tx = rect.width / 2 - cx * sc;
      ty = rect.height / 2 - cy * sc;
    }
  });

  function nodeColor(node: GraphNode): string {
    if (node.isGroup) {
      // Group nodes: muted tones based on dirPath hash
      const hash = (node.dirPath || node.id).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
      return COLORS[hash % COLORS.length];
    }
    return COLORS[(node.community ?? 0) % COLORS.length];
  }

  function edgePathD(points: { x: number; y: number }[]): string {
    if (points.length < 2) return '';
    if (points.length === 2) {
      const [p0, p1] = points;
      const mx = (p0.x + p1.x) / 2;
      const my = (p0.y + p1.y) / 2;
      const dx = p1.x - p0.x;
      const dy = p1.y - p0.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const offset = Math.min(dist * 0.15, 30);
      const nx = -dy / (dist || 1) * offset;
      const ny = dx / (dist || 1) * offset;
      return `M${p0.x},${p0.y} Q${mx + nx},${my + ny} ${p1.x},${p1.y}`;
    }
    let d = `M${points[0].x},${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      const cpx = (prev.x + curr.x) / 2;
      d += ` C${cpx},${prev.y} ${cpx},${curr.y} ${curr.x},${curr.y}`;
    }
    return d;
  }

  function edgeMidpoint(points: { x: number; y: number }[]): { x: number; y: number } {
    if (points.length === 0) return { x: 0, y: 0 };
    if (points.length === 1) return points[0];
    const mid = Math.floor(points.length / 2);
    if (points.length % 2 === 0) {
      return { x: (points[mid - 1].x + points[mid].x) / 2, y: (points[mid - 1].y + points[mid].y) / 2 };
    }
    return points[mid];
  }

  // --- Interaction ---
  function handleWheel(e: WheelEvent) {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    const newSc = Math.max(0.15, Math.min(4, sc * factor));
    const rect = svgEl!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    tx = mx - (mx - tx) * (newSc / sc);
    ty = my - (my - ty) * (newSc / sc);
    sc = newSc;
  }

  function handleMouseDown(e: MouseEvent) {
    if (e.button !== 0) return;
    isPanning = true;
    panStartX = e.clientX - tx;
    panStartY = e.clientY - ty;
  }

  function handleMouseMove(e: MouseEvent) {
    if (isPanning) {
      tx = e.clientX - panStartX;
      ty = e.clientY - panStartY;
      return;
    }
    if (!svgEl) return;
    const pt = svgEl.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return;
    const svgPt = pt.matrixTransform(ctm.inverse());
    const gx = (svgPt.x - tx) / sc;
    const gy = (svgPt.y - ty) / sc;
    let found: string | null = null;
    for (const n of layout.nodes) {
      if (gx >= n.x - n.width / 2 && gx <= n.x + n.width / 2 &&
          gy >= n.y - n.height / 2 && gy <= n.y + n.height / 2) {
        found = n.id;
        break;
      }
    }
    hoveredId = found;
    svgEl.style.cursor = found ? 'pointer' : (isPanning ? 'grabbing' : 'grab');
  }

  function handleMouseUp() {
    isPanning = false;
  }

  let clickTimer: ReturnType<typeof setTimeout> | null = null;

  function handleSvgClick(e: MouseEvent) {
    if (!svgEl) return;
    const pt = svgEl.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return;
    const svgPt = pt.matrixTransform(ctm.inverse());
    const gx = (svgPt.x - tx) / sc;
    const gy = (svgPt.y - ty) / sc;

    for (const n of layout.nodes) {
      if (gx >= n.x - n.width / 2 && gx <= n.x + n.width / 2 &&
          gy >= n.y - n.height / 2 && gy <= n.y + n.height / 2) {
        if (clickTimer) {
          clearTimeout(clickTimer);
          clickTimer = null;
          onnodedblclick?.(n);
        } else {
          const clicked = n;
          clickTimer = setTimeout(() => {
            clickTimer = null;
            onnodeclick?.(clicked);
          }, 250);
        }
        return;
      }
    }
  }

  // --- Minimap ---
  const MINIMAP_W = 180;
  const MINIMAP_H = 120;
  const MINIMAP_PAD = 10;

  let minimapNodes = $derived.by(() => {
    if (layout.nodes.length === 0) return null;
    const xs = layout.nodes.map(n => n.x);
    const ys = layout.nodes.map(n => n.y);
    const minX = Math.min(...xs) - 40;
    const maxX = Math.max(...xs) + 40;
    const minY = Math.min(...ys) - 40;
    const maxY = Math.max(...ys) + 40;
    const rangeX = (maxX - minX) || 1;
    const rangeY = (maxY - minY) || 1;
    const iw = MINIMAP_W - 2 * MINIMAP_PAD;
    const ih = MINIMAP_H - 2 * MINIMAP_PAD;
    const mmScale = Math.min(iw / rangeX, ih / rangeY);
    const drawW = rangeX * mmScale;
    const drawH = rangeY * mmScale;
    const offX = MINIMAP_PAD + (iw - drawW) / 2;
    const offY = MINIMAP_PAD + (ih - drawH) / 2;
    const nodes = layout.nodes.map(n => ({
      id: n.id,
      mx: offX + (n.x - minX) * mmScale,
      my: offY + (n.y - minY) * mmScale,
      color: nodeColor(n),
      isGroup: n.isGroup,
    }));
    return { nodes, bounds: { minX, rangeX, minY, rangeY }, offX, offY, mmScale };
  });

  let minimapViewport = $derived.by(() => {
    if (!minimapNodes || !svgEl) return null;
    const { bounds, offX, offY, mmScale } = minimapNodes;
    const sw = svgEl.clientWidth;
    const sh = svgEl.clientHeight;
    const gx2mx = (v: number) => offX + (v - bounds.minX) * mmScale;
    const gy2my = (v: number) => offY + (v - bounds.minY) * mmScale;
    const l = gx2mx(-tx / sc);
    const t = gy2my(-ty / sc);
    const r = gx2mx((sw - tx) / sc);
    const b = gy2my((sh - ty) / sc);
    const cl = Math.max(0, l);
    const ct = Math.max(0, t);
    const cr = Math.min(MINIMAP_W, r);
    const cb = Math.min(MINIMAP_H, b);
    return { x: cl, y: ct, w: Math.max(0, cr - cl), h: Math.max(0, cb - ct) };
  });

  // --- Minimap drag ---
  let isDraggingMinimap = false;
  let mmDragStartX = 0;
  let mmDragStartY = 0;
  let mmDragStartTx = 0;
  let mmDragStartTy = 0;

  function handleMinimapDragStart(e: MouseEvent) {
    if (!minimapNodes || !svgEl) return;
    e.preventDefault();
    e.stopPropagation();
    isDraggingMinimap = true;
    mmDragStartX = e.clientX;
    mmDragStartY = e.clientY;
    mmDragStartTx = tx;
    mmDragStartTy = ty;
  }

  function handleMinimapDragMove(e: MouseEvent) {
    if (!isDraggingMinimap || !minimapNodes || !svgEl) return;
    const { mmScale } = minimapNodes;
    const dx = e.clientX - mmDragStartX;
    const dy = e.clientY - mmDragStartY;
    const graphDx = dx / mmScale;
    const graphDy = dy / mmScale;
    tx = mmDragStartTx - graphDx * sc;
    ty = mmDragStartTy - graphDy * sc;
  }

  function handleMinimapDragEnd() {
    isDraggingMinimap = false;
  }

  function handleMinimapClick(e: MouseEvent) {
    if (isDraggingMinimap) return;
    if (!minimapNodes || !svgEl) return;
    const { bounds, offX, offY, mmScale } = minimapNodes;
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const gx = (mx - offX) / mmScale + bounds.minX;
    const gy = (my - offY) / mmScale + bounds.minY;
    const sw = svgEl.getBoundingClientRect().width;
    const sh = svgEl.getBoundingClientRect().height;
    tx = sw / 2 - gx * sc;
    ty = sh / 2 - gy * sc;
  }
</script>

<div style="width:100%;height:100%;position:relative;">
<svg
  bind:this={svgEl}
  style="width:100%;height:100%;display:block;background:var(--background-primary);"
  onwheel={handleWheel}
  onmousedown={handleMouseDown}
  onmousemove={handleMouseMove}
  onmouseup={handleMouseUp}
  onmouseleave={handleMouseUp}
  onclick={handleSvgClick}
>
  <defs>
    <marker id="flamme-arrow" viewBox="0 0 10 10" refX="10" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="var(--text-faint)" />
    </marker>
  </defs>

  <g transform="translate({tx},{ty}) scale({sc})">
    <!-- Edges -->
    {#each layout.edges as edge (edge.source + '-' + edge.target)}
      <path
        d={edgePathD(edge.points)}
        fill="none"
        stroke="var(--text-faint)"
        stroke-width={edge.count > 1 ? 2 : 1.2}
        stroke-opacity={edge.count > 1 ? 0.6 : 0.4}
        marker-end="url(#flamme-arrow)"
      />
      <!-- Edge count badge -->
      {#if edge.count > 1}
        {@const mid = edgeMidpoint(edge.points)}
        <rect
          x={mid.x - 10}
          y={mid.y - 8}
          width={20}
          height={16}
          rx="4"
          fill="var(--background-secondary)"
          stroke="var(--background-modifier-border)"
          stroke-width="0.8"
        />
        <text
          x={mid.x}
          y={mid.y + 1}
          text-anchor="middle"
          dominant-baseline="central"
          fill="var(--text-muted)"
          font-size="9"
          font-weight="600"
          style="pointer-events:none;"
        >
          {edge.count}
        </text>
      {/if}
    {/each}

    <!-- Nodes -->
    {#each layout.nodes as node (node.id)}
      {@const color = nodeColor(node)}
      {@const isHov = hoveredId === node.id}
      {@const isMatch = searchQuery && (node.label || node.id).toLowerCase().includes(searchQuery.toLowerCase())}
      {@const dimmed = searchQuery && !isMatch}

      <g
        transform="translate({node.x - node.width / 2},{node.y - node.height / 2})"
        style="opacity:{dimmed ? 0.2 : 1};transition:opacity 0.15s;"
      >
        {#if node.isGroup}
          <!-- ═══ Group node ═══ -->
          <rect
            width={node.width}
            height={node.height}
            rx="10"
            transform="translate(1,2)"
            style="fill:rgba(0,0,0,0.06);"
          />
          <rect
            width={node.width}
            height={node.height}
            rx="10"
            fill={isHov ? '#fff' : 'var(--background-secondary)'}
            stroke={isHov ? color : 'var(--background-modifier-border)'}
            stroke-width={isHov ? 2.5 : 1.5}
            stroke-dasharray="6,3"
          />
          <!-- Expand indicator -->
          <text
            x={12}
            y={node.height / 2}
            dominant-baseline="central"
            fill={color}
            font-size="14"
            style="pointer-events:none;"
          >
            +
          </text>
          <!-- Label -->
          <text
            x={node.width / 2 + 4}
            y={node.height / 2 - 5}
            text-anchor="middle"
            dominant-baseline="central"
            fill={isHov ? color : 'var(--text-normal)'}
            font-size="12"
            font-weight="600"
            style="pointer-events:none;user-select:none;"
          >
            {node.label || node.id}
          </text>
          <!-- Child count -->
          <text
            x={node.width / 2 + 4}
            y={node.height / 2 + 10}
            text-anchor="middle"
            dominant-baseline="central"
            fill="var(--text-faint)"
            font-size="10"
            style="pointer-events:none;"
          >
            {node.childCount ?? 0} 个文件
          </text>
        {:else}
          <!-- ═══ Leaf node ═══ -->
          <rect
            width={node.width}
            height={node.height}
            rx="6"
            transform="translate(1,2)"
            style="fill:rgba(0,0,0,0.06);"
          />
          <rect
            width={node.width}
            height={node.height}
            rx="6"
            fill={isHov ? '#fff' : color}
            stroke={isMatch ? '#fff' : color}
            stroke-width={isHov ? 2.5 : isMatch ? 2.5 : 1}
          />
          {#if isMatch}
            <rect
              width={node.width + 6}
              height={node.height + 6}
              rx="9"
              fill="none"
              stroke={color}
              stroke-width="2"
              transform="translate(-3,-3)"
              style="filter:blur(2px);opacity:0.6;"
            />
          {/if}
          <text
            x={node.width / 2}
            y={node.height / 2}
            text-anchor="middle"
            dominant-baseline="central"
            fill={isHov ? color : '#fff'}
            font-size="11"
            font-weight="500"
            style="pointer-events:none;user-select:none;"
          >
            {node.label || node.id}
          </text>
        {/if}
      </g>
    {/each}
  </g>
</svg>

{#if minimapNodes}
  <div style="position:absolute;bottom:12px;right:12px;background:var(--background-secondary);border:1px solid var(--background-modifier-border);border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.15);">
    <svg
      width={MINIMAP_W}
      height={MINIMAP_H}
      style="display:block;cursor:pointer;"
      onclick={handleMinimapClick}
      onmousemove={handleMinimapDragMove}
      onmouseup={handleMinimapDragEnd}
      onmouseleave={handleMinimapDragEnd}
    >
      {#each minimapNodes.nodes as mn (mn.id)}
        {#if mn.isGroup}
          <rect x={mn.mx - 3} y={mn.my - 3} width={6} height={6} rx={2} fill={mn.color} opacity="0.8" />
        {:else}
          <circle cx={mn.mx} cy={mn.my} r="2" fill={mn.color} opacity="0.7" />
        {/if}
      {/each}
      {#if minimapViewport}
        <rect
          x={minimapViewport.x}
          y={minimapViewport.y}
          width={minimapViewport.w}
          height={minimapViewport.h}
          fill="rgba(255,255,255,0.12)"
          stroke="var(--text-muted)"
          stroke-width="1.5"
          stroke-dasharray="3,2"
          rx="2"
          style="cursor:move;"
          onmousedown={handleMinimapDragStart}
        />
      {/if}
    </svg>
  </div>
{/if}
</div>
