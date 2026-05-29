import { useMemo } from 'react'
import type { Settings } from '../types'
import { flammeKeysFromSettings, type FlammeKeyHeaders } from '../lib/flamme/headers'

export function useFlammeHeaders(settings: Settings): FlammeKeyHeaders {
  return useMemo(
    () => flammeKeysFromSettings(settings),
    [
      settings.flamme_llm_key,
      settings.flamme_embed_key,
      settings.flamme_brain_key,
      settings.flamme_mineru_token,
    ],
  )
}
