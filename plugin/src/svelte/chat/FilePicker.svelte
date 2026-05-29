<script lang="ts">
  import type { App } from 'obsidian';

  let { app, selectedFiles = $bindable() }: { app: App; selectedFiles: string[] } = $props();

  const SOURCE_EXTS = new Set(['pdf', 'excalidraw', 'md']);
  const SKIP_PREFIXES = ['entities/', 'topics/', 'comparisons/', 'explorations/'];

  let showPicker: boolean = $state(false);
  let expandedFolders: Set<string> = $state(new Set());

  interface TreeNode {
    name: string;
    path: string;
    isFolder: boolean;
    children: TreeNode[];
  }

  function isSourceFile(path: string): boolean {
    if (path.startsWith('.') || path.includes('.flamme')) return false;
    return !SKIP_PREFIXES.some(p => path.startsWith(p));
  }

  function buildTree(files: { path: string; basename: string; extension: string }[]): TreeNode[] {
    const root: TreeNode = { name: '', path: '', isFolder: true, children: [] };

    for (const f of files) {
      const parts = f.path.split('/');
      let current = root;
      for (let i = 0; i < parts.length; i++) {
        const isLast = i === parts.length - 1;
        const seg = parts[i];
        const segPath = parts.slice(0, i + 1).join('/');
        if (isLast) {
          current.children.push({
            name: f.basename,
            path: f.path,
            isFolder: false,
            children: [],
          });
        } else {
          let child = current.children.find(c => c.isFolder && c.path === segPath);
          if (!child) {
            child = { name: seg, path: segPath, isFolder: true, children: [] };
            current.children.push(child);
          }
          current = child;
        }
      }
    }

    function sortNode(node: TreeNode) {
      node.children.sort((a, b) => {
        if (a.isFolder !== b.isFolder) return a.isFolder ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      for (const c of node.children) {
        if (c.isFolder) sortNode(c);
      }
    }
    sortNode(root);
    return root.children;
  }

  let tree = $derived(() => {
    const files = app.vault.getFiles()
      .filter(f => SOURCE_EXTS.has(f.extension.toLowerCase()))
      .filter(f => isSourceFile(f.path));

    return buildTree(
      files.map(f => ({ path: f.path, basename: f.basename, extension: f.extension }))
    );
  });

  function toggleFolder(path: string) {
    const next = new Set(expandedFolders);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    expandedFolders = next;
  }

  function toggleFile(path: string) {
    if (selectedFiles.includes(path)) {
      selectedFiles = selectedFiles.filter(f => f !== path);
    } else {
      selectedFiles = [...selectedFiles, path];
    }
  }

  function toggleFolderAll(node: TreeNode) {
    const allPaths = collectFilePaths(node);
    const allSelected = allPaths.every(p => selectedFiles.includes(p));
    if (allSelected) {
      selectedFiles = selectedFiles.filter(f => !allPaths.includes(f));
    } else {
      const newFiles = allPaths.filter(p => !selectedFiles.includes(p));
      selectedFiles = [...selectedFiles, ...newFiles];
    }
  }

  function collectFilePaths(node: TreeNode): string[] {
    if (!node.isFolder) return [node.path];
    return node.children.flatMap(c => collectFilePaths(c));
  }

  function isFolderFullySelected(node: TreeNode): boolean {
    const paths = collectFilePaths(node);
    return paths.length > 0 && paths.every(p => selectedFiles.includes(p));
  }

  function fileIcon(ext: string): string {
    switch (ext.toLowerCase()) {
      case 'pdf': return '📄';
      case 'pptx': case 'ppt': return '📊';
      case 'excalidraw': return '✏️';
      default: return '📝';
    }
  }

  function getFileExt(path: string): string {
    const dot = path.lastIndexOf('.');
    return dot >= 0 ? path.slice(dot + 1) : '';
  }
</script>

{#snippet folderTree(node: TreeNode, depth: number)}
  {#if node.isFolder}
    <div class="flamme-tree-folder" style="padding-left: {depth * 12}px">
      <div class="flamme-tree-row flamme-tree-folder-row" onclick={() => toggleFolder(node.path)}>
        <span class="flamme-tree-arrow">{expandedFolders.has(node.path) ? '▾' : '▸'}</span>
        <input type="checkbox"
          checked={isFolderFullySelected(node)}
          class="flamme-tree-checkbox"
          onclick={(e: Event) => { e.stopPropagation(); toggleFolderAll(node); }}
        />
        <span class="flamme-tree-name">📁 {node.name}/</span>
        <span class="flamme-tree-count">{collectFilePaths(node).length}</span>
      </div>
      {#if expandedFolders.has(node.path)}
        {#each node.children as child}
          {@render folderTree(child, depth + 1)}
        {/each}
      {/if}
    </div>
  {:else}
    <div class="flamme-tree-row flamme-tree-file-row" style="padding-left: {depth * 12 + 14}px" onclick={() => toggleFile(node.path)}>
      <span class="flamme-tree-arrow"></span>
      <input type="checkbox" checked={selectedFiles.includes(node.path)} class="flamme-tree-checkbox" />
      <span class="flamme-tree-name">{fileIcon(getFileExt(node.path))} {node.name}</span>
      <span class="flamme-tree-ext">.{getFileExt(node.path)}</span>
    </div>
  {/if}
{/snippet}

<div class="flamme-file-picker">
  {#if selectedFiles.length > 0}
    <div class="flamme-selected-files">
      {#each selectedFiles as path}
        <span class="flamme-file-chip">
          {fileIcon(getFileExt(path))} {path.split('/').pop()}
          <button class="flamme-chip-remove" onclick={() => toggleFile(path)}>×</button>
        </span>
      {/each}
      <button class="flamme-clear-btn" onclick={() => selectedFiles = []}>清除</button>
    </div>
  {/if}

  <button class="flamme-pick-btn" onclick={() => showPicker = !showPicker}>
    {showPicker ? '▼ 收起文件树' : '▶ 选择学习资料'}
  </button>

  {#if showPicker}
    <div class="flamme-tree">
      {#each tree() as node}
        {@render folderTree(node, 0)}
      {/each}
      {#if tree().length === 0}
        <div class="flamme-tree-empty">暂无可选文件</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .flamme-file-picker { margin: 4px 0; }

  .flamme-selected-files {
    display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px;
  }
  .flamme-file-chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: var(--interactive-accent); color: var(--text-on-accent);
    padding: 2px 8px; border-radius: 4px; font-size: 11px;
  }
  .flamme-chip-remove {
    background: none; border: none; color: var(--text-on-accent);
    cursor: pointer; padding: 0 2px; font-size: 14px; line-height: 1;
  }
  .flamme-clear-btn {
    background: none; border: 1px solid var(--text-muted); color: var(--text-muted);
    padding: 2px 6px; border-radius: 4px; cursor: pointer; font-size: 10px;
  }
  .flamme-pick-btn {
    background: none; border: 1px dashed var(--text-muted); color: var(--text-muted);
    padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;
    width: 100%; text-align: center;
  }

  .flamme-tree {
    margin-top: 4px; border: 1px solid var(--background-modifier-border);
    border-radius: 6px; background: var(--background-secondary);
    max-height: 260px; overflow-y: auto; font-size: 12px;
  }

  .flamme-tree-row {
    display: flex; align-items: center; gap: 2px;
    padding: 3px 6px; cursor: pointer; user-select: none;
  }
  .flamme-tree-row:hover { background: var(--background-modifier-hover); }

  .flamme-tree-arrow {
    width: 14px; text-align: center; flex-shrink: 0; font-size: 10px;
    color: var(--text-muted);
  }
  .flamme-tree-checkbox {
    margin: 0 4px 0 0; flex-shrink: 0; cursor: pointer;
  }
  .flamme-tree-name {
    flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .flamme-tree-count {
    color: var(--text-faint); font-size: 10px; flex-shrink: 0;
  }
  .flamme-tree-ext {
    color: var(--text-faint); font-size: 10px; flex-shrink: 0;
  }
  .flamme-tree-empty {
    padding: 12px; text-align: center; color: var(--text-muted);
  }
</style>
