<script lang="ts">
  import type { Message } from '../../types';
  import MessageContent from './MessageContent.svelte';
  import FlameAvatar from './avatar/FlameAvatar.svelte';
  import type { App } from 'obsidian';
  import { extractSuggestionQuestions } from '../../lib/markdown';

  let { msg, i, app, streaming, onsend, avatarState, isLastAssistant, avatarLabel }: {
    msg: Message;
    i: number;
    app: App;
    streaming: boolean;
    onsend: (text?: string) => void;
    avatarState?: 'peek' | 'look' | 'think' | 'happy' | 'answer' | 'confused';
    isLastAssistant?: boolean;
    avatarLabel?: string;
  } = $props();

  const IDLE_STATES: Array<'peek' | 'look' | 'think' | 'happy' | 'answer' | 'confused'> = ['peek', 'look', 'think', 'happy', 'answer', 'confused'];
  const randomIdleState = IDLE_STATES[Math.floor(Math.random() * IDLE_STATES.length)];

  const STATE_LABELS: Record<string, string> = {
    peek: 'Peeking...',
    look: 'Looking...',
    think: 'Thinking...',
    happy: 'Smiling...',
    answer: 'Answering...',
    confused: 'Wondering...',
  };

  let activeState = $derived(
    isLastAssistant && streaming && avatarState ? avatarState : randomIdleState
  );
  let displayLabel = $derived(STATE_LABELS[activeState]);

  let fallbackSuggestions = $derived(extractSuggestionQuestions(msg.content).questions);
  let suggestionQuestions = $derived(
    msg.suggestedQuestions && msg.suggestedQuestions.length > 0
      ? msg.suggestedQuestions
      : fallbackSuggestions,
  );
</script>

<div data-message-index={i} class="flamme-msg-row" class:user={msg.role === 'user'} class:assistant={msg.role === 'assistant'}>
  {#if msg.toolCalls && msg.toolCalls.length > 0}
    <div class="flamme-tool-badges">
      {#each msg.toolCalls as tc}
        <span class="flamme-tool-badge">{tc}</span>
      {/each}
    </div>
  {/if}

  {#if msg.role === 'assistant'}
    <!-- Assistant: avatar + bubble row -->
    <div class="flamme-assistant-row">
      <div class="flamme-avatar-col">
        <div class="flamme-msg-avatar">
          <FlameAvatar state={activeState} />
        </div>
        <span class="flamme-avatar-label">{displayLabel}</span>
      </div>
      <div style="flex:1;min-width:0;display:flex;flex-direction:column;">
        <div class="flamme-bubble assistant">
          <MessageContent text={msg.content} {app} />
        </div>

        {#if suggestionQuestions.length > 0}
          <div class="flamme-suggestions">
            {#each suggestionQuestions as q}
              <button
                class="flamme-suggestion"
                onclick={() => onsend(q)}
                disabled={streaming}
              >{q}</button>
            {/each}
          </div>
        {/if}

        {#if msg.duration || msg.tokenCount}
          <div class="flamme-msg-stats">
            {#if msg.duration}{msg.duration}s{/if}
            {#if msg.duration && msg.tokenCount}&middot;{/if}
            {#if msg.tokenCount}{msg.tokenCount} tokens{/if}
          </div>
        {/if}
      </div>
    </div>
  {:else}
    <!-- User: green bubble on the right -->
    <div class="flamme-bubble user">
      <span style="white-space:pre-wrap;">{msg.content}</span>
    </div>
  {/if}
</div>
