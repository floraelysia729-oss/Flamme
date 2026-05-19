<script lang="ts">
  let { input = $bindable(''), streaming, onsend, oncancel }: {
    input: string;
    streaming: boolean;
    onsend: (text?: string) => void;
    oncancel: () => void;
  } = $props();

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onsend();
    }
  }
</script>

<div class="flamme-input-bar">
  <div class="flamme-input-row">
    <input
      type="text"
      bind:value={input}
      onkeydown={handleKeydown}
      placeholder="输入消息... (支持自然语言)"
    />
    <button
      onclick={() => streaming ? oncancel() : onsend()}
      class="flamme-send-btn"
      class:streaming
    >
      {streaming ? 'STOP' : 'SEND'}
    </button>
  </div>
</div>
