/** Flamme plugin shared types */

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
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
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FlammeSettings {
  backendUrl: string;
  autoStartBackend: boolean;
  pythonPath: string;
  backendProjectPath: string;
  defaultChatMode: 'search' | 'learn';
  showToolCalls: boolean;
  maxHistorySessions: number;
  // API Keys（用户自带）
  llmApiKey: string;
  embedApiKey: string;
  brainApiKey: string;
  mineruApiToken: string;
}

export const DEFAULT_SETTINGS: FlammeSettings = {
  backendUrl: 'https://flamme.yourdomain.com',
  autoStartBackend: false,
  pythonPath: 'python',
  backendProjectPath: '',
  defaultChatMode: 'search',
  showToolCalls: true,
  maxHistorySessions: 50,
  llmApiKey: '',
  embedApiKey: '',
  brainApiKey: '',
  mineruApiToken: '',
};
