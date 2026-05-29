import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { FLAMME_INDEX_SYNC_DEBOUNCE_MS, useFlammeIndexSync } from './useFlammeIndexSync'
import { VAULT_CHANGED_EVENT } from './useVaultWatcher'

const listenMock = vi.fn()
const syncVaultMock = vi.fn()
const runPipelineMock = vi.fn()

vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => listenMock(...args),
}))

vi.mock('../mock-tauri', () => ({
  isTauri: () => true,
}))

vi.mock('../lib/flamme/client', () => ({
  createFlammeClient: () => ({
    syncVault: syncVaultMock,
    runPipeline: runPipelineMock,
  }),
}))

describe('useFlammeIndexSync', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    listenMock.mockReset()
    syncVaultMock.mockReset()
    runPipelineMock.mockReset()
    syncVaultMock.mockResolvedValue({})
    runPipelineMock.mockResolvedValue({})
    listenMock.mockResolvedValue(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces vault-changed before sync and pipeline', async () => {
    let eventHandler: ((event: { payload: { vaultPath: string; paths: string[] } }) => void) | undefined
    listenMock.mockImplementation(async (eventName, handler) => {
      if (eventName === VAULT_CHANGED_EVENT) {
        eventHandler = handler
      }
      return () => {}
    })

    renderHook(() => useFlammeIndexSync({
      vaultPath: '/vault',
      sidecarPhase: 'healthy',
      apiReachable: true,
    }))

    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      eventHandler?.({ payload: { vaultPath: '/vault', paths: ['note.md'] } })
    })

    expect(syncVaultMock).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(FLAMME_INDEX_SYNC_DEBOUNCE_MS)
      await Promise.resolve()
    })

    expect(syncVaultMock).toHaveBeenCalledWith(false, false)
    expect(runPipelineMock).toHaveBeenCalledWith({
      preset: 'index',
      scope: 'git',
      embed: false,
      graph: false,
    })
  })
})
