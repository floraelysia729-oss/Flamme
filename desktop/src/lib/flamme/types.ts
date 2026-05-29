export interface FlammeStatusResponse {
  total_documents: number
  by_level: Record<string, number>
  total_tags: number
  embeddings: {
    embedded: number
    total: number
  }
  last_updated: string | null
  vault_path: string
  vault_source: string
  db_path: string
}

/** Sidecar process lifecycle (Rust spawn). */
export type FlammeSidecarPhase =
  | 'idle'
  | 'starting'
  | 'healthy'
  | 'failed'
  | 'skipped_dev'

/**
 * UI runtime state — maps to StatusBar §5.5.
 * @deprecated Use FlammeRuntimeState; kept for gradual migration.
 */
export type FlammeHealthState = 'checking' | 'connected' | 'disconnected'

export type FlammeRuntimeState =
  | 'rust_only'
  | 'sidecar_starting'
  | 'indexing_light'
  | 'embedding'
  | 'ready'
  | 'degraded'

export interface FlammeSidecarConfig {
  devSkipSpawn: boolean
  port: number
}

export interface GraphNode {
  id: string
  label: string
  type: string
  level?: string
  community?: number
  val?: number
  source_file?: string
  entity_file?: string
  isGroup?: boolean
  childCount?: number
  dirPath?: string
}

export interface GraphEdge {
  source: string
  target: string
  label: string
  count?: number
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface DirNode {
  id: string
  label: string
  children: DirNode[]
  leafNodeIds: string[]
  totalCount: number
}

export interface AggregatedEdge {
  source: string
  target: string
  count: number
  label: string
}

export interface GraphNeighbor {
  id: string
  label: string
  type: string
  relation: string
}

export interface GraphNeighborsResponse {
  node: string
  neighbors: GraphNeighbor[]
  degree: number
  error?: string
}

export interface GraphStatsResponse {
  nodes: number
  edges: number
  communities?: number
}

export interface PipelineDbStats {
  documents?: number
  entities?: number
  relations?: number
  missing_files?: number
  total_documents?: number
  total_tags?: number
  by_level?: Record<string, number>
  [key: string]: unknown
}

export interface PipelinePlanResponse {
  scope?: string
  pending_count?: number
  estimate_seconds?: number
  scan?: {
    md_new?: string[]
    md_updated?: string[]
    md_removed?: string[]
    binary_unprocessed?: string[]
    missing_embed?: string[]
    [key: string]: unknown
  }
  actions?: string[]
  to_index?: unknown[]
  to_embed?: unknown[]
  to_graph?: unknown[]
  error?: string
  [key: string]: unknown
}

export interface PipelineStatusResponse {
  vault_path: string
  git: Record<string, unknown>
  baseline: Record<string, unknown> | null
  db: PipelineDbStats
  presets: string[]
}
