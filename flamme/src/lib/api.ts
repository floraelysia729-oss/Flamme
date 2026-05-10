const API_BASE = '/api';

export async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
  return resp.json();
}

/** SSE streaming chat — yields parsed events, supports AbortController */
export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
  mode: string = 'search',
): AsyncGenerator<{ type: string; content?: string; questions?: string[] }> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, mode }),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error('Chat stream failed');

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(line.slice(6));
        console.log('[SSE]', event.type, event.content?.slice(0, 80));
        yield event;
        if (event.type === 'done' || event.type === 'error') return;
      } catch { /* skip malformed */ }
    }
  }
}

/** API endpoints */
export const api = {
  status: () => fetchJSON<any>('/status'),
  documents: {
    list: () => fetchJSON<any[]>('/documents'),
    recent: () => fetchJSON<any[]>('/documents/recent'),
  },
  graph: {
    full: () => fetchJSON<{ nodes: any[]; edges: any[] }>('/graph/full'),
    subgraph: (entity: string, depth = 1) =>
      fetchJSON<{ nodes: any[]; edges: any[] }>(`/graph/subgraph?entity=${encodeURIComponent(entity)}&depth=${depth}`),
  },
  agents: {
    list: () => fetchJSON<any[]>('/agents'),
  },
  chat: {
    clear: (sessionId: string) =>
      fetch(`/api/chat/${sessionId}`, { method: 'DELETE' }),
    sessions: () => fetchJSON<{ sessions: Array<{ session_id: string; title: string; message_count: number; last_updated: string }> }>('/chat/sessions'),
    session: (sessionId: string) =>
      fetchJSON<{ session_id: string; messages: Array<{ role: string; content: string }> }>(`/chat/sessions/${sessionId}`),
  },
};
