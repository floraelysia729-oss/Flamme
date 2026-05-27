<script lang="ts">
  import { tick } from 'svelte';
  import type { Message } from '../../types';
  import MessageBubble from './MessageBubble.svelte';
  import type { App } from 'obsidian';

  let {
    messages,
    streaming,
    elapsed,
    app,
    scrollToBottomSignal,
    streamAssistantIndex,
    followAssistantUntilFull,
    avatarState,
    onsend,
  }: {
    messages: Message[];
    streaming: boolean;
    elapsed: number;
    app: App;
    scrollToBottomSignal: number;
    streamAssistantIndex: number | null;
    followAssistantUntilFull: boolean;
    avatarState: 'peek' | 'look' | 'think' | 'happy' | 'answer' | 'confused';
    onsend: (text?: string) => void;
  } = $props();

  let container: HTMLDivElement | undefined = $state();
  let lastScrollSignal = 0;
  let lastAssistantIndex: number | null = null;
  let localFollowAssistant = false;

  function formatElapsed(ms: number): string {
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m${s < 10 ? '0' : ''}${s}s`;
  }

  function scrollToBottom() {
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }

  function followAssistantReplyUntilFull() {
    if (!container || streamAssistantIndex === null || !localFollowAssistant) return;

    const assistantEl = container.querySelector<HTMLDivElement>(
      `[data-message-index="${streamAssistantIndex}"]`,
    );
    if (!assistantEl) return;

    if (assistantEl.offsetHeight < container.clientHeight) {
      scrollToBottom();
      return;
    }

    localFollowAssistant = false;
    container.scrollTop = Math.min(
      assistantEl.offsetTop,
      container.scrollHeight - container.clientHeight,
    );
  }

  $effect(() => {
    const trackedAssistant = streamAssistantIndex === null ? null : messages[streamAssistantIndex];
    messages.length;
    trackedAssistant?.content;
    trackedAssistant?.toolCalls?.length;
    trackedAssistant?.toolStatus?.length;
    trackedAssistant?.toolStatus?.map((ts) => `${ts.name}:${ts.status}:${ts.message ?? ''}`).join('|');
    scrollToBottomSignal;
    streamAssistantIndex;
    followAssistantUntilFull;

    tick().then(() => {
      if (!container) return;

      if (streamAssistantIndex !== lastAssistantIndex) {
        lastAssistantIndex = streamAssistantIndex;
        localFollowAssistant = followAssistantUntilFull;
      }

      if (scrollToBottomSignal !== lastScrollSignal) {
        lastScrollSignal = scrollToBottomSignal;
        scrollToBottom();
        return;
      }

      followAssistantReplyUntilFull();
    });
  });


</script>

<div bind:this={container} class="flamme-messages-area">
  {#if messages.length === 0}
    <div class="flamme-empty-state">
      <p>向知识库提问</p>
      <p>支持自然语言查询和知识库管理</p>
    </div>
  {/if}

  {#each messages as msg, i}
    <MessageBubble
      {msg} {i} {app} {streaming} {onsend}
      avatarState={msg.role === 'assistant' ? avatarState : undefined}
      isLastAssistant={msg.role === 'assistant' && i === messages.length - 1}
      waitElapsed={msg.role === 'assistant' && i === messages.length - 1 && streaming ? elapsed : 0}
    />
  {/each}

  {#if streaming && !messages.some((m, i) => m.role === 'assistant' && i === messages.length - 1 && ((m.toolStatus?.some(ts => ts.status !== 'done')) || m.content))}
    <div class="flamme-thinking">
      思考中... {formatElapsed(Math.max(elapsed, 200))}
    </div>
  {/if}
</div>
