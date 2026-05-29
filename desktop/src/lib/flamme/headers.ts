export interface FlammeKeyHeaders {
  llmKey?: string | null
  embedKey?: string | null
  brainKey?: string | null
  mineruToken?: string | null
}

export function buildFlammeHeaders(
  vaultPath: string,
  keys?: FlammeKeyHeaders,
): Record<string, string> {
  const headers: Record<string, string> = {}
  const trimmed = vaultPath.trim()
  if (trimmed) {
    headers['X-Vault-Path'] = trimmed
  }
  if (keys?.llmKey?.trim()) {
    headers['X-LLM-Key'] = keys.llmKey.trim()
  }
  if (keys?.embedKey?.trim()) {
    headers['X-Embed-Key'] = keys.embedKey.trim()
  }
  if (keys?.brainKey?.trim()) {
    headers['X-Brain-Key'] = keys.brainKey.trim()
  } else if (keys?.llmKey?.trim()) {
    headers['X-Brain-Key'] = keys.llmKey.trim()
  }
  if (keys?.mineruToken?.trim()) {
    headers['X-MinerU-Token'] = keys.mineruToken.trim()
  }
  return headers
}

export function flammeKeysFromSettings(settings: {
  flamme_llm_key?: string | null
  flamme_embed_key?: string | null
  flamme_brain_key?: string | null
  flamme_mineru_token?: string | null
}): FlammeKeyHeaders {
  return {
    llmKey: settings.flamme_llm_key,
    embedKey: settings.flamme_embed_key,
    brainKey: settings.flamme_brain_key,
    mineruToken: settings.flamme_mineru_token,
  }
}
