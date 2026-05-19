<script lang="ts">
  let { mode = $bindable() }: { mode: 'search' | 'learn' } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="flamme-mode-slider" onclick={() => mode = mode === 'search' ? 'learn' : 'search'}>
  <span class="flamme-mode-label" class:active={mode === 'search'}>SEARCH</span>
  <div class="flamme-mode-track">
    <div class="flamme-mode-thumb" class:right={mode === 'learn'}></div>
  </div>
  <span class="flamme-mode-label" class:active={mode === 'learn'}>LEARN</span>
</div>
