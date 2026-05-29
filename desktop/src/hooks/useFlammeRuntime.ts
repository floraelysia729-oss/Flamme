import { useCallback, useEffect, useState } from 'react'
import { checkFlammeProcessAlive, checkFlammeStatus } from '../lib/flamme/health'
import { FLAMME_HEALTH_POLL_MS } from '../lib/flamme/constants'
import type { FlammeKeyHeaders } from '../lib/flamme/headers'
import type { FlammeRuntimeState, FlammeStatusResponse } from '../lib/flamme/types'
import { useFlammeIndexSync } from './useFlammeIndexSync'
import { useFlammeOnDemandPipeline } from './useFlammeOnDemandPipeline'
import { useFlammePipeline } from './useFlammePipeline'
import { useFlammeSidecar } from './useFlammeSidecar'

function deriveRuntimeState(input: {
  vaultPath: string
  sidecarPhase: ReturnType<typeof useFlammeSidecar>['phase']
  apiReachable: boolean
  status: FlammeStatusResponse | null
  indexing: boolean
}): FlammeRuntimeState {
  const { vaultPath, sidecarPhase, apiReachable, status, indexing } = input
  if (!vaultPath.trim()) return 'rust_only'

  if (sidecarPhase === 'starting') return 'sidecar_starting'

  if (!apiReachable) {
    if (sidecarPhase === 'failed') return 'degraded'
    if (sidecarPhase === 'skipped_dev') {
      return 'degraded'
    }
    return sidecarPhase === 'idle' ? 'rust_only' : 'degraded'
  }

  if (indexing) return 'indexing_light'

  const embedded = status?.embeddings?.embedded ?? 0
  const total = status?.embeddings?.total ?? 0
  if (total > 0 && embedded < total) return 'embedding'

  return 'ready'
}

/** @deprecated alias for StatusBar migration */
export function runtimeToHealthState(state: FlammeRuntimeState): 'checking' | 'connected' | 'disconnected' {
  if (state === 'ready' || state === 'embedding' || state === 'indexing_light') return 'connected'
  if (state === 'sidecar_starting') return 'checking'
  return 'disconnected'
}

export function useFlammeRuntime(vaultPath: string, keys?: FlammeKeyHeaders) {
  const sidecar = useFlammeSidecar(vaultPath)
  const [status, setStatus] = useState<FlammeStatusResponse | null>(null)
  const [apiReachable, setApiReachable] = useState(false)
  const [indexing, setIndexing] = useState(false)

  const refreshApi = useCallback(async () => {
    const trimmed = vaultPath.trim()
    if (!trimmed) {
      setStatus(null)
      setApiReachable(false)
      return
    }

    const alive = await checkFlammeProcessAlive()
    if (!alive) {
      setStatus(null)
      setApiReachable(false)
      return
    }

    const result = await checkFlammeStatus(trimmed)
    setStatus(result)
    setApiReachable(!!result)
  }, [vaultPath])

  useEffect(() => {
    void refreshApi()
    const pollMs = (status?.embeddings?.total ?? 0) > (status?.embeddings?.embedded ?? 0)
      ? 5_000
      : FLAMME_HEALTH_POLL_MS
    const id = window.setInterval(() => {
      void refreshApi()
    }, pollMs)
    return () => window.clearInterval(id)
  }, [refreshApi, status?.embeddings?.embedded, status?.embeddings?.total])

  useFlammePipeline({
    vaultPath,
    sidecarPhase: sidecar.phase,
    apiReachable,
    keys,
    onIndexingStart: () => setIndexing(true),
    onIndexingEnd: () => {
      setIndexing(false)
      void refreshApi()
    },
  })

  useFlammeIndexSync({
    vaultPath,
    sidecarPhase: sidecar.phase,
    apiReachable,
    keys,
    onSyncStart: () => setIndexing(true),
    onSyncEnd: () => {
      setIndexing(false)
      void refreshApi()
    },
  })

  const onDemand = useFlammeOnDemandPipeline({
    vaultPath,
    apiReachable,
    keys,
  })

  useEffect(() => {
    onDemand.resetForVault(vaultPath)
  }, [vaultPath, onDemand])

  useEffect(() => {
    if (!apiReachable || !status) return
    const embedded = status.embeddings?.embedded ?? 0
    const total = status.embeddings?.total ?? 0
    if (total > 0 && embedded < total) {
      onDemand.ensureChatEmbeddings(status)
    }
  }, [apiReachable, status?.embeddings?.embedded, status?.embeddings?.total, onDemand, status])

  const state = deriveRuntimeState({
    vaultPath,
    sidecarPhase: sidecar.phase,
    apiReachable,
    status,
    indexing,
  })

  const refresh = useCallback(async () => {
    sidecar.retrySpawn()
    await refreshApi()
  }, [sidecar, refreshApi])

  return {
    state,
    status,
    apiReachable,
    sidecarPhase: sidecar.phase,
    devSkipSpawn: sidecar.config?.devSkipSpawn ?? false,
    refresh,
    isChatReady: state === 'ready' || state === 'embedding' || state === 'indexing_light',
    ensureChatEmbeddings: onDemand.ensureChatEmbeddings,
    ensureGraphBuilt: onDemand.ensureGraphBuilt,
  }
}
