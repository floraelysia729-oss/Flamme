import type { AgentFileCallbacks } from '../aiAgentFileOperations'
import type { AgentStreamCallbacks } from '../../utils/streamAiAgent'
import { applyFlammeFileWrite } from './agentWrite'
import type { FlammeKeyHeaders } from './headers'
import type { ChatStreamEvent } from './sse-chat'
import { streamChat } from './sse-chat'

export interface StreamFlammeChatRequest {
  message: string
  sessionId: string
  vaultPath: string
  mode?: string
  selectedFiles?: string[]
  keys?: FlammeKeyHeaders
  callbacks: AgentStreamCallbacks
  fileCallbacks?: AgentFileCallbacks
  markInternalWrite?: (path: string) => void
  signal?: AbortSignal
}

export async function streamFlammeChat(request: StreamFlammeChatRequest): Promise<void> {
  const {
    message,
    sessionId,
    vaultPath,
    mode,
    selectedFiles,
    keys,
    callbacks,
    fileCallbacks,
    markInternalWrite,
    signal,
  } = request

  try {
    for await (const event of streamChat({
      message,
      sessionId,
      vaultPath,
      mode,
      selectedFiles,
      keys,
      signal,
    })) {
      await applyChatStreamEvent(event, {
        callbacks,
        vaultPath,
        fileCallbacks,
        markInternalWrite,
      })
    }
    callbacks.onDone()
  } catch (error) {
    const messageText = error instanceof Error ? error.message : String(error)
    callbacks.onError(messageText)
    callbacks.onDone()
  }
}

export async function applyChatStreamEvent(
  event: ChatStreamEvent,
  context: {
    callbacks: AgentStreamCallbacks
    vaultPath: string
    fileCallbacks?: AgentFileCallbacks
    markInternalWrite?: (path: string) => void
  },
): Promise<void> {
  const { callbacks, vaultPath, fileCallbacks, markInternalWrite } = context

  switch (event.type) {
    case 'token':
      if (event.content) callbacks.onText(event.content)
      return
    case 'tool_status':
      if (event.status === 'running' || event.status === 'progress') {
        callbacks.onToolStart(event.name ?? 'tool', event.name ?? 'tool', event.message)
        return
      }
      if (event.status === 'done') {
        callbacks.onToolDone(event.name ?? 'tool', event.message)
      }
      return
    case 'tool_call':
      if (event.content) callbacks.onThinking(event.content)
      return
    case 'file_write':
      await applyFlammeFileWrite(event, vaultPath, fileCallbacks, markInternalWrite)
      return
    case 'error':
      callbacks.onError(event.content ?? 'Flamme chat error')
      return
    case 'done':
    case 'heartbeat':
    case 'suggested_questions':
      return
    default:
      return
  }
}
