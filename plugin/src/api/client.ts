/** 获取 Obsidian vault 绝对路径（仅在插件环境可用） */
export function getVaultPath(): string {
  try { return ((window as any).app?.vault?.adapter as any)?.basePath ?? ''; } catch { return ''; }
}

/** HTTP client for the LLM-WIKI backend */
import type { GraphData, FlammeSettings } from '../types';

/** 构建带 API key + vault 路径的 headers（全局共用） */
export function buildAuthHeaders(settings: FlammeSettings, vaultPath?: string): Record<string, string> {
  const headers: Record<string, string> = {};
  if (vaultPath) headers['X-Vault-Path'] = vaultPath;
  if (settings.llmApiKey) headers['X-LLM-Key'] = settings.llmApiKey;
  if (settings.embedApiKey) headers['X-Embed-Key'] = settings.embedApiKey;
  if (settings.llmApiKey) headers['X-Brain-Key'] = settings.llmApiKey;
  if (settings.mineruApiToken) headers['X-MinerU-Token'] = settings.mineruApiToken;
  return headers;
}

export class ApiClient {
  private baseUrl: string;
  private settings: FlammeSettings;

  constructor(settings: FlammeSettings) {
    this.settings = settings;
    this.baseUrl = settings.backendUrl + '/api';
  }

  updateSettings(settings: FlammeSettings) {
    this.settings = settings;
    this.baseUrl = settings.backendUrl + '/api';
  }

  private async fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json', ...buildAuthHeaders(this.settings, getVaultPath()), ...options?.headers },
      ...options,
    });
    if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
    return resp.json();
  }

  // Status
  getStatus() { return this.fetchJSON<any>('/status'); }

  // Chat
  deleteSession(sessionId: string) {
    return this.fetchJSON<void>(`/chat/${sessionId}`, { method: 'DELETE' });
  }
  getSessions() {
    return this.fetchJSON<{ sessions: any[] }>('/chat/sessions');
  }
  getSession(sessionId: string) {
    return this.fetchJSON<any>(`/chat/sessions/${sessionId}`);
  }

  // Documents
  listDocuments(page = 1, perPage = 20, search?: string) {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (search) params.set('search', search);
    return this.fetchJSON<any>(`/documents?${params}`);
  }
  getDocument(path: string) {
    return this.fetchJSON<any>(`/documents/${encodeURIComponent(path)}`);
  }
  searchDocuments(query: string, topK = 5) {
    return this.fetchJSON<any>('/documents/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    });
  }

  // Graph
  getFullGraph() { return this.fetchJSON<GraphData>('/graph/full'); }
  getSubgraph(entity: string, depth = 1) {
    return this.fetchJSON<GraphData>(`/graph/subgraph?entity=${encodeURIComponent(entity)}&depth=${depth}`);
  }
  getNeighbors(node: string) {
    return this.fetchJSON<any>(`/graph/neighbors/${encodeURIComponent(node)}`);
  }
  getGraphStats() { return this.fetchJSON<any>('/graph/stats'); }
  buildGraph() {
    return this.fetchJSON<GraphData>('/graph/build', { method: 'POST' });
  }

  // Ingest
  ingestFile(path: string, level = 'lite') {
    return this.fetchJSON<any>('/ingest', {
      method: 'POST',
      body: JSON.stringify({ path, level }),
    });
  }

  syncVault(embed = false, graph = false) {
    return this.fetchJSON<any>('/ingest/sync', {
      method: 'POST',
      body: JSON.stringify({ embed, graph }),
    });
  }

  // Health check
  async isHealthy(): Promise<boolean> {
    try {
      await this.getStatus();
      return true;
    } catch {
      return false;
    }
  }
}
