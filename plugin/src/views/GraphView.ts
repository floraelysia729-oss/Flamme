import { ItemView, WorkspaceLeaf } from 'obsidian';
import { mount, unmount } from 'svelte';
import GraphContainer from '../svelte/graph/GraphContainer.svelte';
import type FlammePlugin from '../main';

export const VIEW_TYPE_GRAPH = 'flamme-graph';

export class GraphView extends ItemView {
  private component: Record<string, unknown> | null = null;
  private plugin: FlammePlugin;

  constructor(leaf: WorkspaceLeaf, plugin: FlammePlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string { return VIEW_TYPE_GRAPH; }
  getDisplayText(): string { return 'Knowledge Graph'; }
  getIcon(): string { return 'git-fork'; }

  async onOpen() {
    this.containerEl.empty();
    this.containerEl.style.height = '100%';
    this.component = mount(GraphContainer, {
      target: this.containerEl,
      props: {
        plugin: this.plugin,
        app: this.app,
      },
    }) as Record<string, unknown>;
  }

  async onClose() {
    if (this.component) {
      unmount(this.component);
    }
    this.component = null;
  }
}
