import { useCallback, useState } from 'react'
import { Brain, ArrowsClockwise } from '@phosphor-icons/react'
import { createFlammeClient } from '../lib/flamme/client'
import { flammeKeysFromSettings } from '../lib/flamme/headers'
import type { Settings } from '../types'
import { SectionHeading, SettingsGroup, SettingsRow, SettingsSection } from './SettingsControls'
import { Button } from './ui/button'
import { SETTINGS_SECTION_IDS } from './settingsSectionIds'
import { PipelineStatusSummary } from './PipelineStatus/PipelineStatusSummary'

interface FlammeSettingsSectionProps {
  vaultPath?: string
  flammeApiReachable?: boolean
  flammeLlmKey: string
  setFlammeLlmKey: (value: string) => void
  flammeEmbedKey: string
  setFlammeEmbedKey: (value: string) => void
  flammeBrainKey: string
  setFlammeBrainKey: (value: string) => void
  flammeMineruToken: string
  setFlammeMineruToken: (value: string) => void
  onRebuildMessage?: (message: string) => void
}

function KeyInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <SettingsRow label={label}>
      <input
        type="password"
        className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
    </SettingsRow>
  )
}

export function FlammeSettingsSection({
  vaultPath = '',
  flammeApiReachable = false,
  flammeLlmKey,
  setFlammeLlmKey,
  flammeEmbedKey,
  setFlammeEmbedKey,
  flammeBrainKey,
  setFlammeBrainKey,
  flammeMineruToken,
  setFlammeMineruToken,
  onRebuildMessage,
}: FlammeSettingsSectionProps) {
  const [rebuilding, setRebuilding] = useState(false)

  const handleRebuildIndex = useCallback(async () => {
    const trimmedVault = vaultPath.trim()
    if (!trimmedVault || !flammeApiReachable) {
      onRebuildMessage?.('Flamme 引擎未就绪，无法重建索引')
      return
    }
    const confirmed = window.confirm(
      '将执行全库索引（embed + graph），可能耗时较长。是否继续？',
    )
    if (!confirmed) return

    setRebuilding(true)
    try {
      const settings: Settings = {
        auto_pull_interval_minutes: null,
        telemetry_consent: null,
        crash_reporting_enabled: null,
        analytics_enabled: null,
        anonymous_id: null,
        release_channel: null,
        flamme_llm_key: flammeLlmKey || null,
        flamme_embed_key: flammeEmbedKey || null,
        flamme_brain_key: flammeBrainKey || null,
        flamme_mineru_token: flammeMineruToken || null,
      }
      const client = createFlammeClient(trimmedVault, flammeKeysFromSettings(settings))
      await client.runPipeline({
        preset: 'full',
        scope: 'all',
        embed: true,
        graph: true,
      })
      onRebuildMessage?.('全库索引任务已提交')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      onRebuildMessage?.(`重建索引失败：${message}`)
    } finally {
      setRebuilding(false)
    }
  }, [
    vaultPath,
    flammeApiReachable,
    flammeLlmKey,
    flammeEmbedKey,
    flammeBrainKey,
    flammeMineruToken,
    onRebuildMessage,
  ])

  return (
    <SettingsSection id={SETTINGS_SECTION_IDS.flamme}>
      <SectionHeading
        title="Flamme 引擎"
        description="API 密钥仅存于本地设置，经请求 Header 传给 Sidecar（127.0.0.1:8765）。"
        icon={<Brain size={16} aria-hidden="true" />}
      />
      <SettingsGroup>
        <KeyInput
          label="LLM Key (Chat)"
          value={flammeLlmKey}
          onChange={setFlammeLlmKey}
          placeholder="DeepSeek / 兼容 API Key"
        />
        <KeyInput
          label="Embed Key"
          value={flammeEmbedKey}
          onChange={setFlammeEmbedKey}
          placeholder="DashScope Embedding Key"
        />
        <KeyInput
          label="Brain Key"
          value={flammeBrainKey}
          onChange={setFlammeBrainKey}
          placeholder="多 Agent 编排（默认同 LLM Key）"
        />
        <KeyInput
          label="MinerU Token"
          value={flammeMineruToken}
          onChange={setFlammeMineruToken}
          placeholder="PDF 解析 Token"
        />
      </SettingsGroup>

      {vaultPath.trim() ? (
        <div className="mt-4">
          <PipelineStatusSummary
            vaultPath={vaultPath}
            keys={{
              llmKey: flammeLlmKey,
              embedKey: flammeEmbedKey,
              brainKey: flammeBrainKey,
              mineruToken: flammeMineruToken,
            }}
            enabled={flammeApiReachable}
          />
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!flammeApiReachable || !vaultPath.trim() || rebuilding}
          onClick={() => void handleRebuildIndex()}
        >
          <ArrowsClockwise size={14} className={rebuilding ? 'animate-spin' : undefined} />
          {rebuilding ? '重建中…' : '重建全库索引'}
        </Button>
        {!flammeApiReachable ? (
          <span className="text-xs text-muted-foreground">Sidecar 未就绪</span>
        ) : null}
      </div>
    </SettingsSection>
  )
}

export function settingsFlammeFieldsFromDraft(draft: {
  flammeLlmKey: string
  flammeEmbedKey: string
  flammeBrainKey: string
  flammeMineruToken: string
}) {
  return {
    flamme_llm_key: draft.flammeLlmKey.trim() || null,
    flamme_embed_key: draft.flammeEmbedKey.trim() || null,
    flamme_brain_key: draft.flammeBrainKey.trim() || null,
    flamme_mineru_token: draft.flammeMineruToken.trim() || null,
  }
}
