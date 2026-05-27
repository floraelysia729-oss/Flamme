/** SSE streaming chat — async generator from backend */

import type { ToolStatus } from '../types';

export type ChatStreamEvent =
  | { type: 'token'; content?: string }
  | { type: 'tool_status'; name?: string; label?: string; status?: ToolStatus['status']; estimate?: string; elapsed?: number; message?: string; files?: string[] }
  | { type: 'tool_call'; content?: string }
  | { type: 'suggested_questions'; questions?: string[] }
  | { type: 'error'; content?: string }
  | { type: 'done' }
  | { type: 'heartbeat' };

function* drainSseBuffer(buffer: string): Generator<ChatStreamEvent, string> {
  const lines = buffer.split('\n');
  const rest = lines.pop() ?? '';

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    try {
      yield JSON.parse(line.slice(6)) as ChatStreamEvent;
    } catch { /* skip malformed */ }
  }

  return rest;
}

export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
  mode: string = 'search',
  baseUrl: string = 'http://localhost:8765',
  selectedFiles?: string[],
  authHeaders?: Record<string, string>,
): AsyncGenerator<ChatStreamEvent> {
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

  const flush = function* (): Generator<ChatStreamEvent, void, unknown> {
    const drained = drainSseBuffer(buffer);
    let step = drained.next();
    while (!step.done) {
      yield step.value;
      step = drained.next();
    }
    buffer = step.value;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      yield* flush();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    yield* flush();
  }
}
