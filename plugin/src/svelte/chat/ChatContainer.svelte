<script lang="ts">
  import type FlammePlugin from '../../main';
  import type { App } from 'obsidian';
  import MessageList from './MessageList.svelte';
  import ChatInput from './ChatInput.svelte';
  import ModeToggle from './ModeToggle.svelte';
  import FilePicker from './FilePicker.svelte';
  import type { Message, ToolStatus } from '../../types';
  import { extractSuggestionQuestions } from '../../lib/markdown';
  import { ApiClient } from '../../api/client';

  let { plugin, app }: { plugin: FlammePlugin; app: App } = $props();

  let messages: Message[] = $state([]);
  let input: string = $state('');
  let streaming: boolean = $state(false);
  let mode: 'search' | 'learn' = $state(plugin.settings.defaultChatMode);
  let sessionId: string = $state(crypto.randomUUID());
  let elapsed: number = $state(0);
  let abortController: AbortController | null = $state(null);
  let scrollToBottomSignal: number = $state(0);
  let streamAssistantIndex: number | null = $state(null);
  let followAssistantUntilFull: boolean = $state(false);
  
  let avatarState: 'peek' | 'look' | 'think' | 'happy' | 'answer' | 'confused' = $state('look');
  let selectedFiles: string[] = $state([]);

  $effect(() => {
    loadSessionHistory();
  });

  async function loadSessionHistory() {
    try {
      const client = new ApiClient(plugin.settings);
      const data = await client.getSessions();
      if (data.sessions && data.sessions.length > 0) {
        const latest = data.sessions[0];
        sessionId = latest.session_id;
        const sessionData = await client.getSession(latest.session_id);
        if (sessionData.messages && sessionData.messages.length > 0) {
          const loaded: Message[] = [];
          for (const m of sessionData.messages) {
            if (m.role === 'user' || m.role === 'assistant') {
              loaded.push({ role: m.role, content: m.content });
            }
          }
          messages = loaded;
          scrollToBottomSignal++;
        }
      }
    } catch { /* first load, no sessions yet */ }
  }

  export async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;

    cancelStream();
    input = '';
    streaming = true;
    elapsed = 0;
    avatarState = 'think';
    const startTime = Date.now();

    const idx = messages.length;
    streamAssistantIndex = idx + 1;
    followAssistantUntilFull = true;
    scrollToBottomSignal++;
    messages.push({ role: 'user', content: text });
    messages.push({ role: 'assistant', content: '' });

    const controller = new AbortController();
    abortController = controller;

    const timer = setInterval(() => { elapsed = Date.now() - startTime; }, 200);

    const patchAssistant = (patch: Partial<Message>) => {
      messages[idx + 1] = { ...messages[idx + 1], ...patch };
    };

    const applyToolStatus = (event: ToolStatus & { type?: string }) => {
      const list = [...(messages[idx + 1].toolStatus ?? [])];
      const activeIdx = list.findLastIndex(
        (ts) => ts.name === event.name && ts.status !== 'done',
      );

      if (event.status === 'done') {
        if (activeIdx >= 0) {
          list[activeIdx] = {
            ...list[activeIdx],
            status: 'done',
            elapsed: event.elapsed,
          };
        }
      } else if (event.status === 'progress') {
        if (activeIdx >= 0) {
          list[activeIdx] = {
            ...list[activeIdx],
            status: 'progress',
            message: event.message,
          };
        } else {
          list.push(event);
        }
      } else {
        list.push(event);
      }

      patchAssistant({ toolStatus: list });
    };

    try {
      const { streamChat } = await import('../../api/sse');
      const { buildAuthHeaders, getVaultPath } = await import('../../api/client');
      let fullContent = '';
      let tokens = 0;

      for await (const event of streamChat(text, sessionId, controller.signal, mode, plugin.settings.backendUrl, mode === 'learn' ? selectedFiles : undefined, buildAuthHeaders(plugin.settings, getVaultPath()))) {
        if (abortController !== controller) return;

        if (event.type === 'heartbeat') continue;

        if (avatarState === 'think' && event.type === 'token') avatarState = 'answer';

        if (event.type === 'token' && event.content) {
          fullContent += event.content;
          tokens++;
          patchAssistant({
            content: fullContent,
            tokenCount: tokens,
            duration: Math.round((Date.now() - startTime) / 100) / 10,
          });
        } else if (event.type === 'tool_status') {
          avatarState = 'look';
          applyToolStatus(event as ToolStatus & { type?: string });
        } else if (event.type === 'tool_call' && event.content) {
          const toolCalls = [...(messages[idx + 1].toolCalls ?? []), event.content];
          patchAssistant({ toolCalls });
        } else if (event.type === 'error' && event.content) {
          patchAssistant({ content: `${messages[idx + 1].content}\n\n**错误:** ${event.content}`.trim() });
          break;
        } else if (event.type === 'suggested_questions' && event.questions) {
          patchAssistant({ suggestedQuestions: event.questions });
        } else if (event.type === 'done') {
          break;
        }
      }

      const { questions, cleanText } = extractSuggestionQuestions(fullContent);
      if (questions.length > 0) {
        messages[idx + 1] = {
          ...messages[idx + 1],
          content: cleanText,
          suggestedQuestions: questions,
        };
      }
    } catch (e: any) {
      if (abortController !== controller) return;
      if (e.name === 'AbortError') {
        messages[idx + 1].content += '\n\n[已取消]';
      } else {
        messages[idx + 1].content = `**错误:** ${e.message}`;
      }
    } finally {
      clearInterval(timer);
      streaming = false;
      elapsed = 0;
      abortController = null;
      streamAssistantIndex = null;
      followAssistantUntilFull = false;
    }
  }

  function cancelStream() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
  }

  export function newSession() {
    cancelStream();
    sessionId = crypto.randomUUID();
    messages = [];
    scrollToBottomSignal++;
  }
</script>

<div class="flamme-chat" style="position:relative;">
  <!-- Pixel Header -->
  <div class="flamme-header">
    <div class="flamme-header-title">
      <span class="flamme-header-text">Flamme Chat</span>
    </div>
    <div class="flamme-header-actions">
      <ModeToggle bind:mode />
      <button class="flamme-pixel-btn" onclick={newSession}>
        NEW CHAT
      </button>
    </div>
  </div>

  <!-- File Picker (learn mode only) -->
  {#if mode === 'learn'}
    <FilePicker {app} bind:selectedFiles />
  {/if}

  <!-- Messages -->
  <MessageList
    {messages}
    {streaming}
    {elapsed}
    {app}
    {scrollToBottomSignal}
    {streamAssistantIndex}
    {followAssistantUntilFull}
    {avatarState}
    onsend={handleSend}
  />

  <!-- Input -->
  <ChatInput bind:input {streaming} onsend={handleSend} oncancel={cancelStream} />
</div>
