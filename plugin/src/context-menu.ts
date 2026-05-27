import { Menu, Notice } from 'obsidian';
import type FlammePlugin from './main';
import { VIEW_TYPE_CHAT } from './views/ChatView';
import { ApiClient } from './api/client';

export function registerContextMenus(plugin: FlammePlugin) {
  // Editor right-click → "Ask Flamme about this"
  plugin.registerEvent(
    plugin.app.workspace.on('editor-menu', (menu: Menu, editor) => {
      const selection = editor.getSelection();
      if (selection) {
        menu.addItem((item) => {
          item
            .setTitle('Ask Flamme about this')
            .setIcon('message-circle')
            .onClick(() => {
              plugin.activateView(VIEW_TYPE_CHAT);
              setTimeout(() => plugin.chatView?.sendMessage(selection), 200);
            });
        });
      }
    }),
  );

  // File explorer right-click → "Ingest to knowledge base"
  plugin.registerEvent(
    plugin.app.workspace.on('file-menu', (menu: Menu, file) => {
      if (file.extension === 'md') {
        menu.addItem((item) => {
          item
            .setTitle('Ingest to knowledge base')
            .setIcon('flame')
            .onClick(async () => {
              try {
                const client = new ApiClient(plugin.settings);
                await client.ingestFile(file.path, 'lite');
                new Notice(`Ingested: ${file.name}`);
              } catch (e: any) {
                new Notice(`Ingestion failed: ${e.message}`);
              }
            });
        });
      }
    }),
  );
}
