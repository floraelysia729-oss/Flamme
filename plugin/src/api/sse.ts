/** SSE streaming chat — async generator from backend */

export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
  mode: string = 'search',
  baseUrl: string = 'http://localhost:8765',
  selectedFiles?: string[],
  authHeaders?: Record<string, string>,
): AsyncGenerator<{ type: string; content?: string; questions?: string[] }> {
  const resp = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders },
    body: JSON.stringify({ message, session_id: sessionId, mode, selected_files: selectedFiles }),
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
        yield event;
        if (event.type === 'done' || event.type === 'error') return;
      } catch { /* skip malformed */ }
    }
  }
}
