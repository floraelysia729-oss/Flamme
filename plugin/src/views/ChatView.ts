import { ItemView, WorkspaceLeaf } from 'obsidian';
import { mount, unmount } from 'svelte';
import ChatContainer from '../svelte/chat/ChatContainer.svelte';
import type FlammePlugin from '../main';

export const VIEW_TYPE_CHAT = 'flamme-chat';

type ChatComponent = {
  handleSend: (text?: string) => void | Promise<void>;
  newSession: () => void;
};

export class ChatView extends ItemView {
  private component: ChatComponent | null = null;
  private plugin: FlammePlugin;

  constructor(leaf: WorkspaceLeaf, plugin: FlammePlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string { return VIEW_TYPE_CHAT; }
  getDisplayText(): string { return 'Flamme Chat'; }
  getIcon(): string { return 'message-circle'; }

  async onOpen() {
    this.containerEl.empty();
    this.containerEl.style.height = '100%';
    this.component = mount(ChatContainer, {
      target: this.containerEl,
      props: {
        plugin: this.plugin,
        app: this.app,
      },
    }) as ChatComponent;
  }

  async onClose() {
    if (this.component) {
      unmount(this.component);
    }
    this.component = null;
  }

  /** External API: send a message to chat */
  sendMessage(text: string) {
    this.component?.handleSend(text);
  }

  /** External API: new session */
  newSession() {
    this.component?.newSession();
  }
}
