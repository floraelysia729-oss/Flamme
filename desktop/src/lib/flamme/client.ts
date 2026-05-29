import { FLAMME_BASE_URL } from './constants'
import { buildFlammeHeaders, type FlammeKeyHeaders } from './headers'
import type {
  GraphData,
  GraphNeighborsResponse,
  GraphStatsResponse,
  PipelinePlanResponse,
  PipelineStatusResponse,
} from './types'

export interface PipelineRunOptions {
  preset?: string
  scope?: string
  embed?: boolean
  graph?: boolean
  cleanup?: boolean
}

export interface FlammeClientOptions {
  vaultPath: string
  baseUrl?: string
  keys?: FlammeKeyHeaders
}

export class FlammeClient {
  private readonly vaultPath: string
  private readonly baseUrl: string
  private readonly keys?: FlammeKeyHeaders

  constructor(vaultPathOrOptions: string | FlammeClientOptions, baseUrl?: string) {
    if (typeof vaultPathOrOptions === 'string') {
      this.vaultPath = vaultPathOrOptions
      this.baseUrl = baseUrl ?? FLAMME_BASE_URL
    } else {
      this.vaultPath = vaultPathOrOptions.vaultPath
      this.baseUrl = vaultPathOrOptions.baseUrl ?? FLAMME_BASE_URL
      this.keys = vaultPathOrOptions.keys
    }
  }

  private headers(): Record<string, string> {
    return buildFlammeHeaders(this.vaultPath, this.keys)
  }

  private async fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...this.headers(),
        ...options?.headers,
      },
      ...options,
    })
    if (!response.ok) {
      throw new Error(`Flamme API ${response.status}: ${response.statusText}`)
    }
    return await response.json() as T
  }

  getStatus() {
    return this.fetchJSON<Record<string, unknown>>('/status')
  }

  getPipelineStatus() {
    return this.fetchJSON<PipelineStatusResponse>('/pipeline/status')
  }

  getPipelinePlan(scope: 'all' | 'git' = 'git') {
    return this.fetchJSON<PipelinePlanResponse>(`/pipeline/plan?scope=${scope}`)
  }

  runPipeline(options: PipelineRunOptions = {}) {
    const {
      preset = 'index',
      scope = 'git',
      embed = false,
      graph = false,
      cleanup = true,
    } = options
    return this.fetchJSON<Record<string, unknown>>('/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ preset, scope, embed, graph, cleanup }),
    })
  }

  getFullGraph() {
    return this.fetchJSON<GraphData>('/graph/full')
  }

  getSubgraph(entity: string, depth = 1) {
    const params = new URLSearchParams({
      entity,
      depth: String(depth),
    })
    return this.fetchJSON<GraphData>(`/graph/subgraph?${params}`)
  }

  getNeighbors(node: string) {
    return this.fetchJSON<GraphNeighborsResponse>(
      `/graph/neighbors/${encodeURIComponent(node)}`,
    )
  }

  getGraphStats() {
    return this.fetchJSON<GraphStatsResponse>('/graph/stats')
  }

  buildGraph() {
    return this.fetchJSON<GraphData>('/graph/build', { method: 'POST' })
  }

  syncVault(embed = false, graph = false) {
    return this.fetchJSON<Record<string, unknown>>('/ingest/sync', {
      method: 'POST',
      body: JSON.stringify({ embed, graph }),
    })
  }
}

export function createFlammeClient(
  vaultPath: string,
  keys?: FlammeKeyHeaders,
): FlammeClient {
  return new FlammeClient({ vaultPath, keys })
}
