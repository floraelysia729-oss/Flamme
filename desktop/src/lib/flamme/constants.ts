export const FLAMME_ORIGIN = 'http://127.0.0.1:8765'

export const FLAMME_BASE_URL = `${FLAMME_ORIGIN}/api`

export const FLAMME_HEALTH_TIMEOUT_MS = 5_000

export const FLAMME_HEALTH_POLL_MS = 30_000

export const FLAMME_SIDECAR_SPAWN_DEBOUNCE_MS = 300

/** Phase 1: all desktop chat goes through Flamme HTTP. */
export const USE_FLAMME_CHAT = true
