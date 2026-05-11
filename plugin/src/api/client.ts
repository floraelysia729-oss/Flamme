/** HTTP client for the LLM-WIKI backend */
import type { GraphData, FlammeSettings } from '../types';

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

  /** 构建带 API key 的 headers */
  private authHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    if (this.settings.llmApiKey) headers['X-LLM-Key'] = this.settings.llmApiKey;
    if (this.settings.embedApiKey) headers['X-Embed-Key'] = this.settings.embedApiKey;
    if (this.settings.brainApiKey) headers['X-Brain-Key'] = this.settings.brainApiKey;
    if (this.settings.mineruApiToken) headers['X-MinerU-Token'] = this.settings.mineruApiToken;
    return headers;
  }

  private async fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json', ...this.authHeaders(), ...options?.headers },
      ...options,
    });
    if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
    return resp.json();
  }

  // Status
  getStatus() { return this.fetchJSON<any>('/status'); }

  // Chat
  deleteSession(sessionId: string) {
    return fetch(`${this.baseUrl}/chat/${sessionId}`, { method: 'DELETE' });
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

  // Agents
  listAgents() { return this.fetchJSON<any>('/agents'); }

  // Health check
  async isHealthy(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/status`);
      return resp.ok;
    } catch {
      return false;
    }
  }
}
