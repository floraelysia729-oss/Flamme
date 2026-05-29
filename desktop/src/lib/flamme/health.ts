import { FLAMME_BASE_URL, FLAMME_HEALTH_TIMEOUT_MS, FLAMME_ORIGIN } from './constants'
import { buildFlammeHeaders } from './headers'
import type { FlammeStatusResponse } from './types'

export async function checkFlammeProcessAlive(): Promise<boolean> {
  try {
    const response = await fetch(`${FLAMME_ORIGIN}/`, {
      signal: AbortSignal.timeout(FLAMME_HEALTH_TIMEOUT_MS),
    })
    return response.ok
  } catch {
    return false
  }
}

export async function checkFlammeStatus(
  vaultPath: string,
): Promise<FlammeStatusResponse | null> {
  if (!vaultPath.trim()) return null

  try {
    const response = await fetch(`${FLAMME_BASE_URL}/status`, {
      headers: buildFlammeHeaders(vaultPath),
      signal: AbortSignal.timeout(FLAMME_HEALTH_TIMEOUT_MS),
    })
    if (!response.ok) return null
    return await response.json() as FlammeStatusResponse
  } catch {
    return null
  }
}
