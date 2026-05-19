<script lang="ts">
  import type { App } from 'obsidian';
  import { renderMarkdown } from '../../lib/markdown';
  import { openAndHighlight } from '../../lib/highlight';

  let { text, app }: { text: string; app: App } = $props();

  let renderedHtml = $derived(renderMarkdown(text));

  function handleClick(event: MouseEvent) {
    const target = (event.target as HTMLElement).closest('.flamme-wikilink');
    if (!target) return;
    const noteName = (target as HTMLElement).dataset.target;
    if (!noteName) return;
    // Open note with automatic paragraph highlighting (searches note content for entity name)
    openAndHighlight(app, noteName);
  }
</script>

{#if text}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="flamme-message-content" onclick={handleClick}>
    {@html renderedHtml}
  </div>
{/if}
