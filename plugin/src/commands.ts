import { Notice } from 'obsidian';
import type FlammePlugin from './main';
import { VIEW_TYPE_CHAT } from './views/ChatView';
import { VIEW_TYPE_GRAPH } from './views/GraphView';
import { ApiClient } from './api/client';

export function registerCommands(plugin: FlammePlugin) {
  plugin.addCommand({
    id: 'open-chat',
    name: 'Open Flamme Chat',
    callback: () => plugin.activateView(VIEW_TYPE_CHAT),
  });

  plugin.addCommand({
    id: 'open-graph',
    name: 'Open Knowledge Graph',
    callback: () => plugin.activateView(VIEW_TYPE_GRAPH),
  });

  plugin.addCommand({
    id: 'new-chat',
    name: 'New Chat Session',
    callback: () => {
      plugin.activateView(VIEW_TYPE_CHAT);
      plugin.chatView?.newSession();
    },
  });

  plugin.addCommand({
    id: 'ask-selection',
    name: 'Ask Flamme about selection',
    editorCallback: (editor) => {
      const selection = editor.getSelection();
      if (selection) {
        plugin.activateView(VIEW_TYPE_CHAT);
        // Small delay to let view open
        setTimeout(() => plugin.chatView?.sendMessage(selection), 200);
      }
    },
  });

  plugin.addCommand({
    id: 'ingest-current',
    name: 'Ingest current file to knowledge base',
    editorCallback: async (_editor, view) => {
      const path = view.file?.path;
      if (!path) return;
      try {
        const client = new ApiClient(plugin.settings);
        await client.ingestFile(path, 'lite');
        new Notice(`Ingested: ${path}`);
      } catch (e: any) {
        new Notice(`Ingest failed: ${e.message}`);
      }
    },
  });
}
