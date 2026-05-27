<script lang="ts">
  import type FlammePlugin from '../../main';
  import type { App } from 'obsidian';
  import type { GraphData, GraphNode } from '../../types';
  import GraphCanvas from './GraphCanvas.svelte';
  import { MarkdownRenderer, Component, TFile } from 'obsidian';
  import { buildDirTree, computeVisibleGraph, computeBreadcrumb, collapseTo, expandAll } from './hierarchy';
  import { ApiClient } from '../../api/client';

  let { plugin, app }: { plugin: FlammePlugin; app: App } = $props();

  let apiClient: ApiClient = $derived(new ApiClient(plugin.settings));

  let graphData: GraphData | null = $state(null);
  let loading: boolean = $state(true);
  let selectedNode: GraphNode | null = $state(null);
  let searchQuery: string = $state('');
  let error: string = $state('');
  let panelEl: HTMLDivElement | undefined = $state();
  let mdComponent: Component | null = null;

  // ── Hierarchy state ──
  let expanded: Set<string> = $state(new Set());
  let canvasKey = $state(0); // force re-mount on expand/collapse

  let dirTree = $derived(graphData ? buildDirTree(graphData) : null);
  let visibleGraph = $derived(
    graphData && dirTree
      ? computeVisibleGraph(graphData, dirTree, expanded)
      : null
  );
  let breadcrumb = $derived(computeBreadcrumb(expanded));

  // Convert AggregatedEdge[] to GraphEdge[] for GraphCanvas compatibility
  let displayData: GraphData | null = $derived(
    visibleGraph
      ? { nodes: visibleGraph.nodes, edges: visibleGraph.edges.map(e => ({ source: e.source, target: e.target, label: e.count > 1 ? `${e.label} ×${e.count}` : e.label, count: e.count })) }
      : null
  );

  async function loadGraph() {
    loading = true;
    error = '';
    try {
      graphData = await apiClient.getFullGraph();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function buildGraph() {
    loading = true;
    try {
      graphData = await apiClient.buildGraph();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function loadSourceDoc(node: GraphNode) {
    // Group nodes don't have source docs
    if (node.isGroup) return;
    if (mdComponent) {
      mdComponent.unload();
      mdComponent = null;
    }
    if (!panelEl) return;
    panelEl.empty();
    panelEl.textContent = '加载文档...';

    const previewPath = node.source_file;
    if (!previewPath) {
      panelEl.textContent = '该节点无关联源文件';
      return;
    }
    const sourcePath = previewPath;

    try {
      const file = app.vault.getAbstractFileByPath(sourcePath);
      if (file instanceof TFile) {
        if (sourcePath.endsWith('.pdf')) {
          panelEl.empty();
          const iframe = panelEl.createEl('iframe');
          iframe.src = app.vault.getResourcePath(file);
          iframe.style.cssText = 'width:100%;height:calc(100vh - 160px);border:none;border-radius:4px;';
        } else if (/\.(png|jpe?g|gif|svg|webp|bmp)$/i.test(sourcePath)) {
          panelEl.empty();
          const img = panelEl.createEl('img');
          img.src = app.vault.getResourcePath(file);
          img.style.cssText = 'max-width:100%;border-radius:4px;';
        } else {
          const content = await app.vault.read(file);
          panelEl.empty();
          mdComponent = new Component();
          mdComponent.load();
          await MarkdownRenderer.render(app, content, panelEl, sourcePath, mdComponent);
        }
      } else {
        const data = await apiClient.getDocument(sourcePath);
        const text = data.content || data.text || '';
        if (text) {
          panelEl.empty();
          mdComponent = new Component();
          mdComponent.load();
          await MarkdownRenderer.render(app, text, panelEl, sourcePath, mdComponent);
        } else if (data.error) {
          panelEl.textContent = data.error;
        } else {
          panelEl.textContent = '文档内容为空';
        }
      }
    } catch (e: any) {
      panelEl.textContent = e.message;
    }
  }

  function handleNodeClick(node: GraphNode) {
    selectedNode = node;
    if (!node.isGroup) {
      loadSourceDoc(node);
    }
  }

  function handleNodeDblClick(node: GraphNode) {
    if (node.isGroup && node.dirPath) {
      // Toggle expand/collapse for group node
      const next = new Set(expanded);
      if (next.has(node.dirPath)) {
        // Collapse: remove this and all deeper
        for (const p of expanded) {
          if (p === node.dirPath || p.startsWith(node.dirPath + '/')) {
            next.delete(p);
          }
        }
      } else {
        next.add(node.dirPath);
      }
      expanded = next;
      canvasKey++;
      return;
    }
    // Leaf node: open source file
    const label = node.source_file || node.label;
    app.workspace.openLinkText(label, '', false);
  }

  function handleBreadcrumbClick(dirPath: string) {
    expanded = collapseTo(expanded, dirPath);
    canvasKey++;
  }

  function handleCollapseAll() {
    expanded = new Set();
    canvasKey++;
  }

  function handleExpandAll() {
    if (dirTree) {
      expanded = expandAll(dirTree);
      canvasKey++;
    }
  }

  // Load on mount
  $effect(() => { loadGraph(); });
</script>

<div style="display:flex;height:100%;">
  <!-- Graph area -->
  <div style="flex:1;position:relative;overflow:hidden;">
    <!-- Toolbar -->
    <div style="position:absolute;top:12px;left:12px;z-index:10;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="搜索节点..."
        style="padding:6px 10px;border-radius:6px;border:1px solid var(--background-modifier-border);background:var(--background-primary);font-size:13px;width:160px;color:var(--text-normal);"
      />
      <button
        onclick={buildGraph}
        disabled={loading}
        style="padding:6px 12px;border-radius:6px;border:1px solid var(--background-modifier-border);background:var(--background-primary);font-size:12px;cursor:pointer;color:var(--text-normal);"
      >
        重建
      </button>
      <button
        onclick={handleCollapseAll}
        style="padding:6px 10px;border-radius:6px;border:1px solid var(--background-modifier-border);background:var(--background-primary);font-size:12px;cursor:pointer;color:var(--text-normal);"
      >
        全部折叠
      </button>
      <button
        onclick={handleExpandAll}
        style="padding:6px 10px;border-radius:6px;border:1px solid var(--background-modifier-border);background:var(--background-primary);font-size:12px;cursor:pointer;color:var(--text-normal);"
      >
        全部展开
      </button>
    </div>

    <!-- Breadcrumb -->
    {#if breadcrumb.length > 0}
      <div style="position:absolute;top:46px;left:12px;z-index:10;display:flex;gap:4px;align-items:center;font-size:12px;">
        <button
          onclick={handleCollapseAll}
          style="padding:2px 8px;border-radius:4px;border:1px solid var(--background-modifier-border);background:var(--background-secondary);font-size:11px;cursor:pointer;color:var(--text-muted);"
        >
          vault
        </button>
        {#each breadcrumb as seg, i}
          <span style="color:var(--text-faint);">/</span>
          {#if i < breadcrumb.length - 1}
            <button
              onclick={() => handleBreadcrumbClick(seg)}
              style="padding:2px 8px;border-radius:4px;border:1px solid var(--background-modifier-border);background:var(--background-secondary);font-size:11px;cursor:pointer;color:var(--text-muted);"
            >
              {seg.split('/').pop()}
            </button>
          {:else}
            <span style="padding:2px 8px;color:var(--text-normal);font-size:11px;">
              {seg.split('/').pop()}
            </span>
          {/if}
        {/each}
      </div>
    {/if}

    {#if loading}
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">
        加载图谱...
      </div>
    {:else if error}
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">
        <p>错误: {error}</p>
      </div>
    {:else if displayData && displayData.nodes.length > 0}
      <GraphCanvas
        key={canvasKey}
        data={displayData}
        {searchQuery}
        onnodeclick={handleNodeClick}
        onnodedblclick={handleNodeDblClick}
      />
    {:else}
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">
        <p>图谱为空，请先运行图谱构建</p>
      </div>
    {/if}
  </div>

  <!-- Right panel: source document viewer -->
  <div style="width:320px;display:flex;flex-direction:column;background:var(--background-secondary);border-left:1px solid var(--background-modifier-border);overflow:hidden;">
    {#if selectedNode}
      <!-- Header -->
      <div style="padding:12px 16px;border-bottom:1px solid var(--background-modifier-border);flex-shrink:0;">
        <h3 style="font-size:14px;font-weight:600;margin:0 0 4px 0;color:var(--text-normal);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          {selectedNode.isGroup ? '📁 ' : ''}{selectedNode.label || selectedNode.id}
        </h3>
        <div style="font-size:11px;color:var(--text-faint);display:flex;gap:8px;flex-wrap:wrap;">
          {#if selectedNode.isGroup}
            <span>目录</span>
            <span>{selectedNode.childCount} 个文件</span>
          {:else}
            {#if selectedNode.type}
              <span>{selectedNode.type}</span>
            {/if}
            {#if selectedNode.community != null}
              <span>社区 {selectedNode.community}</span>
            {/if}
            {#if selectedNode.val}
              <span>{selectedNode.val} 连接</span>
            {/if}
          {/if}
        </div>
        {#if selectedNode.isGroup}
          <div style="margin-top:6px;font-size:11px;color:var(--text-faint);">
            双击展开/折叠
          </div>
          <button
            onclick={() => handleNodeDblClick(selectedNode!)}
            style="margin-top:8px;padding:4px 10px;border-radius:4px;border:1px solid var(--background-modifier-border);background:var(--interactive-accent);font-size:11px;cursor:pointer;color:var(--text-on-accent);width:100%;"
          >
            {expanded.has(selectedNode.dirPath || '') ? '折叠' : '展开'}
          </button>
        {:else}
          {#if selectedNode.source_file}
            <div style="margin-top:6px;font-size:11px;color:var(--text-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title={selectedNode.source_file}>
              源文件: {selectedNode.source_file.split('/').pop()}
            </div>
          {/if}
          <button
            onclick={() => handleNodeDblClick(selectedNode!)}
            style="margin-top:8px;padding:4px 10px;border-radius:4px;border:1px solid var(--background-modifier-border);background:var(--interactive-accent);font-size:11px;cursor:pointer;color:var(--text-on-accent);width:100%;"
          >
            打开源文件
          </button>
        {/if}
      </div>

      <!-- Document content -->
      <div style="flex:1;overflow:auto;padding:12px 16px;">
        <div bind:this={panelEl} class="flamme-doc-render" style="font-size:13px;line-height:1.6;"></div>
      </div>
    {:else}
      <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:16px;">
        <p style="font-size:12px;color:var(--text-faint);text-align:center;">
          点击节点查看源文档<br/>双击分组展开<br/>双击文件打开笔记
        </p>
      </div>
    {/if}
  </div>
</div>
