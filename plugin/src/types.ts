/** Flamme plugin shared types */

export interface ToolStatus {
  name: string;
  label: string;
  status: 'running' | 'progress' | 'done';
  estimate?: string;
  elapsed?: number;
  message?: string;
  files?: string[];
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  toolStatus?: ToolStatus[];
  duration?: number;
  tokenCount?: number;
  suggestedQuestions?: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  level?: string;
  community?: number;
  val?: number;
  source_file?: string;
  /** @deprecated use source_file — entity files now use source_file directly */
  entity_file?: string;
  // Hierarchy fields (synthetic group nodes)
  isGroup?: boolean;
  childCount?: number;
  dirPath?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
  count?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface DirNode {
  id: string;           // canonical path: "lite/微积分②"
  label: string;        // last segment: "微积分②"
  children: DirNode[];
  leafNodeIds: string[];
  totalCount: number;   // recursive leaf count
}

export interface AggregatedEdge {
  source: string;
  target: string;
  count: number;
  label: string;
}

export interface FlammeSettings {
  backendUrl: string;
  defaultChatMode: 'search' | 'learn';
  showToolCalls: boolean;
  maxHistorySessions: number;
  // API Keys（用户自带）
  llmApiKey: string;
  embedApiKey: string;
  mineruApiToken: string;
}

export const DEFAULT_SETTINGS: FlammeSettings = {
  backendUrl: 'http://localhost:8765',
  defaultChatMode: 'search',
  showToolCalls: true,
  maxHistorySessions: 50,
  llmApiKey: '',
  embedApiKey: '',
  mineruApiToken: '',
};
