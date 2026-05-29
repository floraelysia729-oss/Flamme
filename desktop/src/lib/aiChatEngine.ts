import type { Settings } from '../types'

export type AiChatEngine = 'flamme' | 'external'

const SUPPORTED_ENGINES: readonly AiChatEngine[] = ['flamme', 'external']

export function normalizeAiChatEngine(value: string | null | undefined): AiChatEngine | null {
  const trimmed = value?.trim().toLowerCase()
  if (!trimmed) return null
  return SUPPORTED_ENGINES.includes(trimmed as AiChatEngine) ? (trimmed as AiChatEngine) : null
}

/** Default chat engine; legacy `default_ai_agent` does not override this. */
export function resolveAiChatEngine(
  settings: Pick<Settings, 'ai_chat_engine'> | null | undefined,
): AiChatEngine {
  return normalizeAiChatEngine(settings?.ai_chat_engine ?? undefined) ?? 'flamme'
}

export function isExternalAiChatEngine(
  settings: Pick<Settings, 'ai_chat_engine'> | null | undefined,
): boolean {
  return resolveAiChatEngine(settings) === 'external'
}

export function isFlammeAiChatEngine(
  settings: Pick<Settings, 'ai_chat_engine'> | null | undefined,
): boolean {
  return resolveAiChatEngine(settings) === 'flamme'
}
