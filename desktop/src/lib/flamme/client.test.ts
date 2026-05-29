import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { FlammeClient, createFlammeClient } from './client'

describe('FlammeClient', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends vault and key headers on graph requests', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [] }),
    } as Response)

    const client = createFlammeClient('/vault', {
      llmKey: 'llm-key',
      embedKey: 'embed-key',
    })

    await client.getFullGraph()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/graph/full'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Vault-Path': '/vault',
          'X-LLM-Key': 'llm-key',
          'X-Embed-Key': 'embed-key',
        }),
      }),
    )
  })

  it('posts pipeline run with preset options', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    } as Response)

    const client = new FlammeClient('/vault')
    await client.runPipeline({ preset: 'full', scope: 'all', embed: true, graph: true })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/pipeline/run'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          preset: 'full',
          scope: 'all',
          embed: true,
          graph: true,
          cleanup: true,
        }),
      }),
    )
  })

  it('syncVault posts ingest/sync body', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ synced: 1 }),
    } as Response)

    const client = new FlammeClient('/vault')
    await client.syncVault(false, false)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/ingest/sync'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ embed: false, graph: false }),
      }),
    )
  })

  it('getNeighbors encodes node name', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ node: 'A', neighbors: [], degree: 0 }),
    } as Response)

    const client = new FlammeClient('/vault')
    await client.getNeighbors('Node/Name')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/graph/neighbors/Node%2FName'),
      expect.any(Object),
    )
  })
})
