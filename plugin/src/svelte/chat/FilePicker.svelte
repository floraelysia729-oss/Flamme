<script lang="ts">
  import type { App } from 'obsidian';

  let { app, selectedFiles = $bindable() }: { app: App; selectedFiles: string[] } = $props();

  const SOURCE_EXTS = new Set(['pdf', 'excalidraw', 'md']);

  let showPicker: boolean = $state(false);
  let expandedFolders: Set<string> = $state(new Set(['pro', 'lite']));

  // Build tree from vault files
  interface TreeNode {
    name: string;
    path: string;
    isFolder: boolean;
    children: TreeNode[];
  }

  let tree = $derived(() => {
    const files = app.vault.getFiles()
      .filter(f => SOURCE_EXTS.has(f.extension.toLowerCase()))
      .filter(f => !f.path.startsWith('.'))
      .filter(f => !f.path.includes('.flamme'))
      .filter(f => !f.path.startsWith('entities/'));

    const root: TreeNode[] = [];

    for (const level of ['pro', 'lite']) {
      const levelFiles = files.filter(f => f.path.startsWith(level + '/'));
      if (levelFiles.length === 0) continue;

      const levelNode: TreeNode = { name: level, path: level, isFolder: true, children: [] };

      for (const f of levelFiles) {
        const parts = f.path.split('/');
        // parts: ['pro', '课程名', '文件.pdf'] or ['pro', '文件.pdf']
        if (parts.length === 2) {
          // Direct file under level
          levelNode.children.push({ name: f.basename, path: f.path, isFolder: false, children: [] });
        } else if (parts.length >= 3) {
          // File in subfolder
          const folderName = parts[1];
          let folder = levelNode.children.find(c => c.name === folderName && c.isFolder);
          if (!folder) {
            folder = { name: folderName, path: `${level}/${folderName}`, isFolder: true, children: [] };
            levelNode.children.push(folder);
          }
          folder.children.push({ name: f.basename, path: f.path, isFolder: false, children: [] });
        }
      }

      // Sort: folders first, then files
      levelNode.children.sort((a, b) => {
        if (a.isFolder !== b.isFolder) return a.isFolder ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      for (const child of levelNode.children) {
        if (child.isFolder) {
          child.children.sort((a, b) => a.name.localeCompare(b.name));
        }
      }

      root.push(levelNode);
    }

    return root;
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

  function isFolderPartiallySelected(node: TreeNode): boolean {
    const paths = collectFilePaths(node);
    return paths.some(p => selectedFiles.includes(p)) && !isFolderFullySelected(node);
  }

  function fileIcon(ext: string): string {
    switch (ext.toLowerCase()) {
      case 'pdf': return '📄';
      case 'pptx': case 'ppt': return '📊';
      case 'excalidraw': return '✏️';
      default: return '📄';
    }
  }

  function getFileExt(path: string): string {
    const dot = path.lastIndexOf('.');
    return dot >= 0 ? path.slice(dot + 1) : '';
  }
</script>

<div class="flamme-file-picker">
  <!-- Selected files chips -->
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

  <!-- Toggle picker -->
  <button class="flamme-pick-btn" onclick={() => showPicker = !showPicker}>
    {showPicker ? '▼ 收起文件树' : '▶ 选择学习资料'}
  </button>

  <!-- File tree -->
  {#if showPicker}
    <div class="flamme-tree">
      {#each tree() as levelNode}
        <div class="flamme-tree-level">
          <!-- Level header (pro/lite) -->
          <div class="flamme-tree-row flamme-tree-level-row" onclick={() => toggleFolder(levelNode.path)}>
            <span class="flamme-tree-arrow">{expandedFolders.has(levelNode.path) ? '▾' : '▸'}</span>
            <input type="checkbox"
              checked={isFolderFullySelected(levelNode)}
              class="flamme-tree-checkbox"
              onclick={(e: Event) => { e.stopPropagation(); toggleFolderAll(levelNode); }}
            />
            <span class="flamme-tree-name flamme-tree-level-name">📁 {levelNode.name}/</span>
            <span class="flamme-tree-count">{collectFilePaths(levelNode).length}</span>
          </div>

          <!-- Expanded content -->
          {#if expandedFolders.has(levelNode.path)}
            {#each levelNode.children as child}
              {#if child.isFolder}
                <!-- Subfolder -->
                <div class="flamme-tree-folder">
                  <div class="flamme-tree-row flamme-tree-folder-row" onclick={() => toggleFolder(child.path)}>
                    <span class="flamme-tree-arrow">{expandedFolders.has(child.path) ? '▾' : '▸'}</span>
                    <input type="checkbox"
                      checked={isFolderFullySelected(child)}
                      class="flamme-tree-checkbox"
                      onclick={(e: Event) => { e.stopPropagation(); toggleFolderAll(child); }}
                    />
                    <span class="flamme-tree-name">📁 {child.name}/</span>
                    <span class="flamme-tree-count">{child.children.length}</span>
                  </div>
                  {#if expandedFolders.has(child.path)}
                    {#each child.children as file}
                      <div class="flamme-tree-row flamme-tree-file-row" onclick={() => toggleFile(file.path)}>
                        <span class="flamme-tree-arrow"></span>
                        <input type="checkbox"
                          checked={selectedFiles.includes(file.path)}
                          class="flamme-tree-checkbox"
                        />
                        <span class="flamme-tree-name">{fileIcon(getFileExt(file.path))} {file.name}</span>
                        <span class="flamme-tree-ext">.{getFileExt(file.path)}</span>
                      </div>
                    {/each}
                  {/if}
                </div>
              {:else}
                <!-- Direct file under level -->
                <div class="flamme-tree-row flamme-tree-file-row" onclick={() => toggleFile(child.path)}>
                  <span class="flamme-tree-arrow"></span>
                  <input type="checkbox"
                    checked={selectedFiles.includes(child.path)}
                    class="flamme-tree-checkbox"
                  />
                  <span class="flamme-tree-name">{fileIcon(getFileExt(child.path))} {child.name}</span>
                  <span class="flamme-tree-ext">.{getFileExt(child.path)}</span>
                </div>
              {/if}
            {/each}
          {/if}
        </div>
      {/each}

      {#if tree().length === 0}
        <div class="flamme-tree-empty">暂无可选文件（PDF/PPT/Excalidraw）</div>
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

  /* Tree */
  .flamme-tree {
    margin-top: 4px; border: 1px solid var(--background-modifier-border);
    border-radius: 6px; background: var(--background-secondary);
    max-height: 260px; overflow-y: auto; font-size: 12px;
  }
  .flamme-tree-level { border-bottom: 1px solid var(--background-modifier-border); }
  .flamme-tree-level:last-child { border-bottom: none; }

  .flamme-tree-row {
    display: flex; align-items: center; gap: 2px;
    padding: 3px 6px; cursor: pointer; user-select: none;
  }
  .flamme-tree-row:hover { background: var(--background-modifier-hover); }

  .flamme-tree-level-row {
    padding: 5px 6px; font-weight: 600;
  }
  .flamme-tree-folder-row { padding-left: 14px; }
  .flamme-tree-file-row { padding-left: 28px; }

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
  .flamme-tree-level-name { color: var(--text-normal); }
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
