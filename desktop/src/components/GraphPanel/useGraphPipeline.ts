import { useEffect, useRef } from 'react'
import { createFlammeClient } from '../../lib/flamme/client'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'

interface UseGraphPipelineOptions {
  vaultPath: string
  keys?: FlammeKeyHeaders
  onEnsureGraphBuilt?: () => Promise<void>
}

export function useGraphPipeline({
  vaultPath,
  keys,
  onEnsureGraphBuilt,
}: UseGraphPipelineOptions) {
  const triggered = useRef(false)

  useEffect(() => {
    const trimmed = vaultPath.trim()
    if (!trimmed || triggered.current) return

    triggered.current = true
    const client = createFlammeClient(trimmed, keys)

    void (async () => {
      if (onEnsureGraphBuilt) {
        await onEnsureGraphBuilt()
        return
      }
      try {
        const stats = await client.getGraphStats()
        if ((stats.nodes ?? 0) > 0) return
        await client.runPipeline({
          preset: 'full',
          scope: 'git',
          embed: true,
          graph: true,
        })
      } catch (error) {
        triggered.current = false
        console.warn('[Flamme] graph pipeline on mount failed:', error)
      }
    })()
  }, [vaultPath, keys, onEnsureGraphBuilt])

  useEffect(() => {
    if (!vaultPath.trim()) {
      triggered.current = false
    }
  }, [vaultPath])
}
