import { describe, expect, it, vi } from 'vitest'
import type { AgentStreamCallbacks } from '../../utils/streamAiAgent'
import { applyChatStreamEvent } from './sse-adapter'

function createCallbacks(overrides: Partial<AgentStreamCallbacks> = {}): AgentStreamCallbacks {
  return {
    onText: vi.fn(),
    onThinking: vi.fn(),
    onToolStart: vi.fn(),
    onToolDone: vi.fn(),
    onError: vi.fn(),
    onDone: vi.fn(),
    ...overrides,
  }
}

describe('applyChatStreamEvent', () => {
  it('maps token events to onText', async () => {
    const callbacks = createCallbacks()
    await applyChatStreamEvent({ type: 'token', content: 'hi' }, {
      callbacks,
      vaultPath: '/vault',
    })
    expect(callbacks.onText).toHaveBeenCalledWith('hi')
  })

  it('maps error events to onError', async () => {
    const callbacks = createCallbacks()
    await applyChatStreamEvent({ type: 'error', content: 'boom' }, {
      callbacks,
      vaultPath: '/vault',
    })
    expect(callbacks.onError).toHaveBeenCalledWith('boom')
  })

  it('handles file_write events via applyFlammeFileWrite', async () => {
    const onFileCreated = vi.fn()
    const markInternalWrite = vi.fn()
    const callbacks = createCallbacks()

    await applyChatStreamEvent({
      type: 'file_write',
      path: 'entities/Test.md',
      content: '# Test',
      mode: 'create',
    }, {
      callbacks,
      vaultPath: '/vault',
      fileCallbacks: { onFileCreated },
      markInternalWrite,
    })

    expect(markInternalWrite).toHaveBeenCalledWith('/vault/entities/Test.md')
    expect(onFileCreated).toHaveBeenCalledWith('entities/Test.md')
  })
})
