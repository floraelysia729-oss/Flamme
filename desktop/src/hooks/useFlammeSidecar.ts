import { useCallback, useEffect, useRef, useState } from 'react'
import { isTauri } from '../mock-tauri'
import { FLAMME_SIDECAR_SPAWN_DEBOUNCE_MS } from '../lib/flamme/constants'
import type { FlammeSidecarConfig, FlammeSidecarPhase } from '../lib/flamme/types'

async function loadSidecarConfig(): Promise<FlammeSidecarConfig> {
  if (!isTauri()) {
    return { devSkipSpawn: true, port: 8765 }
  }
  const { invoke } = await import('@tauri-apps/api/core')
  const raw = await invoke<{ devSkipSpawn: boolean; port: number }>('get_flamme_sidecar_config')
  return raw
}

export function useFlammeSidecar(vaultPath: string) {
  const [phase, setPhase] = useState<FlammeSidecarPhase>('idle')
  const [config, setConfig] = useState<FlammeSidecarConfig | null>(null)
  const lastSpawnedVault = useRef('')

  useEffect(() => {
    void loadSidecarConfig().then(setConfig)
  }, [])

  const spawn = useCallback(async (path: string) => {
    const trimmed = path.trim()
    if (!trimmed) {
      setPhase('idle')
      lastSpawnedVault.current = ''
      return
    }

    if (!isTauri()) {
      setPhase('skipped_dev')
      return
    }

    const cfg = config ?? await loadSidecarConfig()
    if (cfg.devSkipSpawn) {
      setPhase('skipped_dev')
      return
    }

    if (lastSpawnedVault.current === trimmed) {
      return
    }

    setPhase('starting')
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const result = await invoke<string>('spawn_flamme_sidecar_command', { vaultPath: trimmed })
      lastSpawnedVault.current = trimmed
      if (result === 'healthy' || result === 'started_unhealthy') {
        setPhase('healthy')
        return
      }
      if (result === 'skipped_dev') {
        setPhase('skipped_dev')
        return
      }
      setPhase('failed')
    } catch {
      setPhase('failed')
    }
  }, [config])

  useEffect(() => {
    const trimmed = vaultPath.trim()
    if (!trimmed) {
      setPhase('idle')
      lastSpawnedVault.current = ''
      return
    }

    if (!isTauri()) {
      setPhase('skipped_dev')
      return
    }

    if (!config) return

    if (lastSpawnedVault.current !== trimmed) {
      lastSpawnedVault.current = ''
    }

    const timer = window.setTimeout(() => {
      void spawn(trimmed)
    }, FLAMME_SIDECAR_SPAWN_DEBOUNCE_MS)

    return () => window.clearTimeout(timer)
  }, [vaultPath, config, spawn])

  const retry = useCallback(() => {
    lastSpawnedVault.current = ''
    void spawn(vaultPath)
  }, [spawn, vaultPath])

  return {
    phase,
    config,
    retrySpawn: retry,
  }
}
