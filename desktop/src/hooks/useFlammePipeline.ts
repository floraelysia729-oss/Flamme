import { useEffect, useRef } from 'react'
import { createFlammeClient } from '../lib/flamme/client'
import type { FlammeKeyHeaders } from '../lib/flamme/headers'
import type { FlammeSidecarPhase } from '../lib/flamme/types'

interface UseFlammePipelineOptions {
  vaultPath: string
  sidecarPhase: FlammeSidecarPhase
  apiReachable: boolean
  keys?: FlammeKeyHeaders
  onIndexingStart?: () => void
  onIndexingEnd?: () => void
}

export function useFlammePipeline({
  vaultPath,
  sidecarPhase,
  apiReachable,
  keys,
  onIndexingStart,
  onIndexingEnd,
}: UseFlammePipelineOptions) {
  const scheduledVault = useRef('')

  useEffect(() => {
    const trimmed = vaultPath.trim()
    if (!trimmed || !apiReachable) return

    const sidecarReady = sidecarPhase === 'healthy' || sidecarPhase === 'skipped_dev'
    if (!sidecarReady) return

    if (scheduledVault.current === trimmed) return
    scheduledVault.current = trimmed

    onIndexingStart?.()
    const client = createFlammeClient(trimmed, keys)
    void client
      .runPipeline({
        preset: 'index',
        scope: 'git',
        embed: false,
        graph: false,
      })
      .catch((error) => {
        console.warn('[Flamme] pipeline index+git failed:', error)
      })
      .finally(() => {
        onIndexingEnd?.()
      })
  }, [vaultPath, sidecarPhase, apiReachable, keys, onIndexingStart, onIndexingEnd])

  useEffect(() => {
    if (!vaultPath.trim()) {
      scheduledVault.current = ''
    }
  }, [vaultPath])
}
