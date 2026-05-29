import { useCallback, useRef } from 'react'
import { createFlammeClient } from '../lib/flamme/client'
import type { FlammeKeyHeaders } from '../lib/flamme/headers'
import type { FlammeStatusResponse } from '../lib/flamme/types'

interface UseFlammeOnDemandPipelineOptions {
  vaultPath: string
  apiReachable: boolean
  keys?: FlammeKeyHeaders
}

export function useFlammeOnDemandPipeline({
  vaultPath,
  apiReachable,
  keys,
}: UseFlammeOnDemandPipelineOptions) {
  const embedInFlight = useRef(false)
  const graphFullScheduled = useRef(false)

  const resetForVault = useCallback((nextVault: string) => {
    if (!nextVault.trim()) {
      embedInFlight.current = false
      graphFullScheduled.current = false
    }
  }, [])

  const ensureChatEmbeddings = useCallback((status: FlammeStatusResponse | null) => {
    const trimmed = vaultPath.trim()
    if (!trimmed || !apiReachable || embedInFlight.current) return

    const embedded = status?.embeddings?.embedded ?? 0
    const total = status?.embeddings?.total ?? 0
    if (total > 0 && embedded >= total) return

    embedInFlight.current = true
    const client = createFlammeClient(trimmed, keys)
    void client
      .runPipeline({
        preset: 'index',
        scope: 'all',
        embed: true,
        graph: false,
      })
      .catch((error) => {
        console.warn('[Flamme] embed pipeline failed:', error)
      })
      .finally(() => {
        embedInFlight.current = false
      })
  }, [vaultPath, apiReachable, keys])

  const ensureGraphBuilt = useCallback(async () => {
    const trimmed = vaultPath.trim()
    if (!trimmed || !apiReachable || graphFullScheduled.current) return

    const client = createFlammeClient(trimmed, keys)
    try {
      const stats = await client.getGraphStats()
      if ((stats.nodes ?? 0) > 0) return

      graphFullScheduled.current = true
      await client.runPipeline({
        preset: 'full',
        scope: 'git',
        embed: true,
        graph: true,
      })
    } catch (error) {
      graphFullScheduled.current = false
      console.warn('[Flamme] graph full pipeline failed:', error)
    }
  }, [vaultPath, apiReachable, keys])

  return {
    ensureChatEmbeddings,
    ensureGraphBuilt,
    resetForVault,
  }
}
