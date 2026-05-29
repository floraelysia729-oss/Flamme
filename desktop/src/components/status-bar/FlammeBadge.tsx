import { useState } from 'react'
import { Brain, CircleNotch as Loader2 } from '@phosphor-icons/react'
import { ActionTooltip } from '@/components/ui/action-tooltip'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { FlammeKeyHeaders } from '../../lib/flamme/headers'
import type { FlammeRuntimeState } from '../../lib/flamme/types'
import { PipelineStatusPanel } from '../PipelineStatus/PipelineStatusPanel'
import { SEP_STYLE } from './styles'

interface FlammeStatusPopoverProps {
  state: FlammeRuntimeState
  vaultPath?: string
  keys?: FlammeKeyHeaders
  embeddingProgress?: { embedded: number; total: number } | null
  onRetry?: () => void
  showSeparator?: boolean
  compact?: boolean
}

function labelForState(
  state: FlammeRuntimeState,
  embeddingProgress?: { embedded: number; total: number } | null,
): string {
  if (state === 'embedding' && embeddingProgress && embeddingProgress.total > 0) {
    return `Flamme · 嵌入 ${embeddingProgress.embedded}/${embeddingProgress.total}`
  }
  switch (state) {
    case 'sidecar_starting':
      return 'Flamme · 启动中…'
    case 'indexing_light':
      return 'Flamme · 同步变更'
    case 'embedding':
      return 'Flamme · 嵌入中'
    case 'ready':
      return 'Flamme · 已就绪'
    case 'degraded':
      return 'Flamme · 离线（仅编辑）'
    case 'rust_only':
    default:
      return 'Flamme · 未连接'
  }
}

function tooltipForState(state: FlammeRuntimeState): string {
  switch (state) {
    case 'ready':
      return '点击查看索引流水线状态'
    case 'embedding':
      return 'Flamme 正在后台嵌入向量，点击查看进度'
    case 'indexing_light':
      return 'Flamme 正在同步 git 变更到索引'
    case 'sidecar_starting':
      return '正在启动 Flamme AI 引擎…'
    case 'degraded':
      return 'Flamme 未就绪。点击重试或查看详情'
    case 'rust_only':
      return '打开 vault 后将自动启动 Flamme 引擎'
    default:
      return 'Flamme 未连接'
  }
}

function colorForState(state: FlammeRuntimeState): string {
  if (state === 'ready') return 'var(--accent-green)'
  if (state === 'sidecar_starting' || state === 'indexing_light' || state === 'embedding') {
    return 'var(--muted-foreground)'
  }
  if (state === 'degraded') return 'var(--accent-orange)'
  return 'var(--muted-foreground)'
}

export function FlammeStatusPopover({
  state,
  vaultPath = '',
  keys,
  embeddingProgress,
  onRetry,
  showSeparator = true,
  compact = false,
}: FlammeStatusPopoverProps) {
  const [open, setOpen] = useState(false)

  if (state === 'rust_only') return null

  const label = labelForState(state, embeddingProgress)
  const color = colorForState(state)
  const spinning = state === 'sidecar_starting' || state === 'indexing_light'
  const apiEnabled = state !== 'degraded' && state !== 'rust_only'

  return (
    <>
      {showSeparator ? <span style={SEP_STYLE} aria-hidden="true" /> : null}
      <Popover open={open} onOpenChange={setOpen}>
        <ActionTooltip copy={{ label: tooltipForState(state) }} side="top">
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className={compact
                ? 'h-6 w-6 rounded-sm p-0 text-muted-foreground hover:text-foreground'
                : 'h-6 px-2 text-[12px] font-medium text-muted-foreground hover:text-foreground'}
              aria-label={label}
              data-testid="status-flamme"
              data-flamme-state={state}
            >
              {spinning
                ? <Loader2 size={13} className="animate-spin" style={{ color }} />
                : <Brain size={13} style={{ color }} />}
              {compact ? null : label}
            </Button>
          </PopoverTrigger>
        </ActionTooltip>
        <PopoverContent align="end" className="w-80 p-4">
          <div className="mb-3 text-sm font-semibold">Flamme 流水线</div>
          <PipelineStatusPanel
            vaultPath={vaultPath}
            keys={keys}
            enabled={apiEnabled}
            embeddingProgress={embeddingProgress}
          />
          {state === 'degraded' && onRetry ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3 w-full"
              onClick={() => {
                onRetry()
                setOpen(false)
              }}
            >
              重试连接
            </Button>
          ) : null}
        </PopoverContent>
      </Popover>
    </>
  )
}

/** @deprecated Use FlammeStatusPopover */
export function FlammeBadge(props: FlammeStatusPopoverProps) {
  return <FlammeStatusPopover {...props} />
}
