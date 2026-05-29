import { invoke } from '@tauri-apps/api/core'
import { isTauri, mockInvoke } from '../../mock-tauri'
import type { AgentFileCallbacks } from '../aiAgentFileOperations'

export interface FlammeFileWriteEvent {
  path?: string
  content?: string
  mode?: 'create' | 'update'
}

export async function applyFlammeFileWrite(
  event: FlammeFileWriteEvent,
  vaultPath: string,
  callbacks?: AgentFileCallbacks,
  markInternalWrite?: (path: string) => void,
): Promise<void> {
  const relativePath = event.path?.trim()
  const content = event.content
  const vaultRoot = vaultPath.trim()
  if (!relativePath || content === undefined || !vaultRoot) return

  const normalizedRelative = relativePath.replace(/\\/g, '/')
  const absolutePath = `${vaultRoot.replace(/\\/g, '/').replace(/\/+$/, '')}/${normalizedRelative}`

  markInternalWrite?.(absolutePath)

  const args = {
    relativePath: normalizedRelative,
    content,
    mode: event.mode ?? 'create',
    vaultPath: vaultRoot,
  }

  if (isTauri()) {
    await invoke<void>('create_note_from_agent', args)
  } else {
    await mockInvoke<void>('create_note_from_agent', args)
  }

  if (event.mode === 'update') {
    callbacks?.onFileModified?.(normalizedRelative)
  } else {
    callbacks?.onFileCreated?.(normalizedRelative)
  }
}
