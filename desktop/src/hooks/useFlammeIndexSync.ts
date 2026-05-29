import { useEffect, useRef } from 'react'
import { listen } from '@tauri-apps/api/event'
import { isTauri } from '../mock-tauri'
import { createFlammeClient } from '../lib/flamme/client'
import type { FlammeKeyHeaders } from '../lib/flamme/headers'
import type { FlammeSidecarPhase } from '../lib/flamme/types'
import { VAULT_CHANGED_EVENT } from './useVaultWatcher'

export const FLAMME_INDEX_SYNC_DEBOUNCE_MS = 5000

interface VaultChangedPayload {
  vaultPath: string
  paths: string[]
}

interface UseFlammeIndexSyncOptions {
  vaultPath: string
  sidecarPhase: FlammeSidecarPhase
  apiReachable: boolean
  keys?: FlammeKeyHeaders
  onSyncStart?: () => void
  onSyncEnd?: () => void
}

export function useFlammeIndexSync({
  vaultPath,
  sidecarPhase,
  apiReachable,
  keys,
  onSyncStart,
  onSyncEnd,
}: UseFlammeIndexSyncOptions) {
  const timerRef = useRef<number | null>(null)
  const syncingRef = useRef(false)

  useEffect(() => {
    if (!isTauri()) return

    const trimmedVault = vaultPath.trim()
    if (!trimmedVault) return

    const sidecarReady = sidecarPhase === 'healthy' || sidecarPhase === 'skipped_dev'
    if (!sidecarReady || !apiReachable) return

    const runSync = () => {
      if (syncingRef.current) return
      syncingRef.current = true
      onSyncStart?.()

      const client = createFlammeClient(trimmedVault, keys)
      void client
        .syncVault(false, false)
        .catch((error) => {
          console.warn('[Flamme] ingest/sync failed:', error)
        })
        .then(() => client.runPipeline({
          preset: 'index',
          scope: 'git',
          embed: false,
          graph: false,
        }))
        .catch((error) => {
          console.warn('[Flamme] index sync pipeline failed:', error)
        })
        .finally(() => {
          syncingRef.current = false
          onSyncEnd?.()
        })
    }

    const scheduleSync = () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
      }
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        runSync()
      }, FLAMME_INDEX_SYNC_DEBOUNCE_MS)
    }

    let unlisten: (() => void) | undefined
    void listen<VaultChangedPayload>(VAULT_CHANGED_EVENT, (event) => {
      const payloadVault = event.payload.vaultPath?.trim()
      if (payloadVault && payloadVault !== trimmedVault) return
      scheduleSync()
    }).then((fn) => {
      unlisten = fn
    })

    return () => {
      unlisten?.()
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [vaultPath, sidecarPhase, apiReachable, keys, onSyncStart, onSyncEnd])
}
