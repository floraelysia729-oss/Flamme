import { App, PluginSettingTab, Setting, Notice } from 'obsidian';
import type FlammePlugin from './main';

export class FlammeSettingTab extends PluginSettingTab {
  plugin: FlammePlugin;

  constructor(app: App, plugin: FlammePlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl('h2', { text: 'Flamme' });

    // ── 连接 ──
    containerEl.createEl('h3', { text: '连接' });

    new Setting(containerEl)
      .setName('Backend URL')
      .setDesc('后端服务地址（云端或本地）')
      .addText(text => text
        .setPlaceholder('https://flamme.yourdomain.com')
        .setValue(this.plugin.settings.backendUrl)
        .onChange(async (value) => {
          this.plugin.settings.backendUrl = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Test Connection')
      .setDesc('检查后端是否可达')
      .addButton(btn => btn
        .setButtonText('Test')
        .onClick(async () => {
          try {
            const resp = await fetch(`${this.plugin.settings.backendUrl}/api/status`);
            if (resp.ok) {
              const data = await resp.json();
              new Notice(`Flamme: Connected — ${data.total_documents} docs`);
            } else {
              new Notice(`Flamme: Connection failed — HTTP ${resp.status}`);
            }
          } catch (e: any) {
            new Notice(`Flamme: Connection failed — ${e.message}`);
          }
        }));

    // ── API Keys ──
    containerEl.createEl('h3', { text: 'API Keys' });

    new Setting(containerEl)
      .setName('LLM API Key')
      .setDesc('Chat 模型（DeepSeek / OpenAI 兼容）')
      .addText(text => text
        .setPlaceholder('sk-...')
        .setValue(this.plugin.settings.llmApiKey)
        .onChange(async (value) => {
          this.plugin.settings.llmApiKey = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Embedding API Key')
      .setDesc('向量嵌入（DashScope / OpenAI 兼容）')
      .addText(text => text
        .setPlaceholder('sk-...')
        .setValue(this.plugin.settings.embedApiKey)
        .onChange(async (value) => {
          this.plugin.settings.embedApiKey = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Brain API Key')
      .setDesc('多 Agent 编排（智谱 GLM）')
      .addText(text => text
        .setPlaceholder('sk-...')
        .setValue(this.plugin.settings.brainApiKey)
        .onChange(async (value) => {
          this.plugin.settings.brainApiKey = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('MinerU Token')
      .setDesc('PDF 精准解析')
      .addText(text => text
        .setPlaceholder('token...')
        .setValue(this.plugin.settings.mineruApiToken)
        .onChange(async (value) => {
          this.plugin.settings.mineruApiToken = value;
          await this.plugin.saveSettings();
        }));

    // ── 本地模式（高级）──
    containerEl.createEl('h3', { text: '本地模式（高级）' });

    new Setting(containerEl)
      .setName('Auto-start backend')
      .setDesc('Obsidian 启动时自动启动本地 Python 后端')
      .addToggle(toggle => toggle
        .setValue(this.plugin.settings.autoStartBackend)
        .onChange(async (value) => {
          this.plugin.settings.autoStartBackend = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Python path')
      .setDesc('本地 Python 路径')
      .addText(text => text
        .setPlaceholder('python')
        .setValue(this.plugin.settings.pythonPath)
        .onChange(async (value) => {
          this.plugin.settings.pythonPath = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Backend project path')
      .setDesc('llm-wiki-2 项目目录（本地模式必填）')
      .addText(text => text
        .setPlaceholder('/path/to/llm-wiki-2')
        .setValue(this.plugin.settings.backendProjectPath)
        .onChange(async (value) => {
          this.plugin.settings.backendProjectPath = value;
          await this.plugin.saveSettings();
        }));

    // ── 偏好 ──
    containerEl.createEl('h3', { text: '偏好' });

    new Setting(containerEl)
      .setName('Default chat mode')
      .setDesc('新对话默认模式')
      .addDropdown(dropdown => dropdown
        .addOption('search', '搜索')
        .addOption('learn', '学习')
        .setValue(this.plugin.settings.defaultChatMode)
        .onChange(async (value: string) => {
          this.plugin.settings.defaultChatMode = value as 'search' | 'learn';
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Show tool calls')
      .setDesc('在聊天消息中显示工具调用标记')
      .addToggle(toggle => toggle
        .setValue(this.plugin.settings.showToolCalls)
        .onChange(async (value) => {
          this.plugin.settings.showToolCalls = value;
          await this.plugin.saveSettings();
        }));
  }
}
