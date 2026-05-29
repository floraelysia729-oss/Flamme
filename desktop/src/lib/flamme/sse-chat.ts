import { FLAMME_ORIGIN } from './constants'
import { buildFlammeHeaders, type FlammeKeyHeaders } from './headers'

export type ChatStreamEvent =
  | { type: 'token'; content?: string }
  | { type: 'tool_status'; name?: string; label?: string; status?: string; message?: string }
  | { type: 'tool_call'; content?: string }
  | { type: 'file_write'; path?: string; content?: string; mode?: 'create' | 'update' }
  | { type: 'suggested_questions'; questions?: string[] }
  | { type: 'error'; content?: string }
  | { type: 'done' }
  | { type: 'heartbeat' }

function* drainSseBuffer(buffer: string): Generator<ChatStreamEvent, string> {
  const lines = buffer.split('\n')
  const rest = lines.pop() ?? ''

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    try {
      yield JSON.parse(line.slice(6)) as ChatStreamEvent
    } catch {
      // skip malformed
    }
  }

  return rest
}

export interface StreamChatOptions {
  message: string
  sessionId: string
  vaultPath: string
  mode?: string
  selectedFiles?: string[]
  signal?: AbortSignal
  baseUrl?: string
  keys?: FlammeKeyHeaders
}

export async function* streamChat(options: StreamChatOptions): AsyncGenerator<ChatStreamEvent> {
  const {
    message,
    sessionId,
    vaultPath,
    mode = 'search',
    selectedFiles,
    signal,
    baseUrl = FLAMME_ORIGIN,
    keys,
  } = options

  const response = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildFlammeHeaders(vaultPath, keys),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      mode,
      selected_files: selectedFiles,
    }),
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const flush = function* (): Generator<ChatStreamEvent, void, unknown> {
    const drained = drainSseBuffer(buffer)
    let step = drained.next()
    while (!step.done) {
      yield step.value
      step = drained.next()
    }
    buffer = step.value
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      yield* flush()
      break
    }

    buffer += decoder.decode(value, { stream: true })
    yield* flush()
  }
}
