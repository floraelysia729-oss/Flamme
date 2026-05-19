import { Plugin } from 'obsidian';
import type { FlammeSettings } from './types';
import { DEFAULT_SETTINGS } from './types';
import { ChatView, VIEW_TYPE_CHAT } from './views/ChatView';
import { GraphView, VIEW_TYPE_GRAPH } from './views/GraphView';
import { FlammeSettingTab } from './settings';
import { registerCommands } from './commands';
import { registerContextMenus } from './context-menu';

export default class FlammePlugin extends Plugin {
  settings: FlammeSettings = DEFAULT_SETTINGS;
  chatView: ChatView | null = null;

  async onload() {
    await this.loadSettings();

    // Load KaTeX CSS programmatically (@import in styles.css doesn't work in Obsidian)
    this.loadKatexCss();

    // Register views
    this.registerView(VIEW_TYPE_CHAT, (leaf) => {
      this.chatView = new ChatView(leaf, this);
      return this.chatView;
    });
    this.registerView(VIEW_TYPE_GRAPH, (leaf) => new GraphView(leaf, this));

    // Ribbon icons
    this.addRibbonIcon('message-circle', 'Flamme Chat', () => {
      this.activateView(VIEW_TYPE_CHAT);
    });
    this.addRibbonIcon('git-fork', 'Flamme Graph', () => {
      this.activateView(VIEW_TYPE_GRAPH);
    });

    // Commands & context menus
    registerCommands(this);
    registerContextMenus(this);

    // Settings tab
    this.addSettingTab(new FlammeSettingTab(this.app, this));
  }

  onunload() {
    document.getElementById('flamme-katex-css')?.remove();
    this.app.workspace.detachLeavesOfType(VIEW_TYPE_CHAT);
    this.app.workspace.detachLeavesOfType(VIEW_TYPE_GRAPH);
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async activateView(viewType: string) {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(viewType)[0];
    if (!leaf) {
      const rightLeaf = workspace.getLeaf('tab');
      await rightLeaf.setViewState({ type: viewType, active: true });
      leaf = rightLeaf;
    }
    workspace.revealLeaf(leaf);
  }

  private loadKatexCss() {
    const el = document.createElement('link');
    el.id = 'flamme-katex-css';
    el.rel = 'stylesheet';
    // pluginDir is the folder containing manifest.json
    el.href = `${(this.app.vault.adapter as any).basePath}/.obsidian/plugins/flamme/katex.min.css`;
    document.head.appendChild(el);
  }
}
