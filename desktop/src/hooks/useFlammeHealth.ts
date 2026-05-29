import { useCallback, useEffect, useState } from 'react'
import { checkFlammeStatus } from '../lib/flamme/health'
import { FLAMME_HEALTH_POLL_MS } from '../lib/flamme/constants'
import type { FlammeHealthState, FlammeStatusResponse } from '../lib/flamme/types'

export function useFlammeHealth(vaultPath: string) {
  const [state, setState] = useState<FlammeHealthState>('checking')
  const [status, setStatus] = useState<FlammeStatusResponse | null>(null)

  const refresh = useCallback(async () => {
    if (!vaultPath.trim()) {
      setState('disconnected')
      setStatus(null)
      return
    }

    setState('checking')
    const result = await checkFlammeStatus(vaultPath)
    if (result) {
      setStatus(result)
      setState('connected')
      return
    }

    setStatus(null)
    setState('disconnected')
  }, [vaultPath])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      void refresh()
    }, FLAMME_HEALTH_POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  return {
    state,
    status,
    refresh,
  }
}
