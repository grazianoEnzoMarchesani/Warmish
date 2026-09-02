<script lang="ts">
  import type { Tool } from './tools';

  let { tool, onpick }: { tool: Tool; onpick: (t: Tool) => void } = $props();

  const items: { id: Tool; label: string; key: string; path: string }[] = [
    { id: 'pan', label: 'Sposta', key: 'V', path: 'M6 3l14 7-6 2-2 6-6-15z' },
    { id: 'rect', label: 'Rettangolo', key: 'R', path: 'M4 6h16v12H4z' },
    { id: 'spot', label: 'Punto', key: 'S', path: 'M12 4v16 M4 12h16 M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0' },
    { id: 'polygon', label: 'Poligono', key: 'P', path: 'M12 3l9 6.5-3.4 10.5H6.4L3 9.5z' },
  ];
</script>

<div class="rail" role="toolbar" aria-label="Strumenti aree">
  {#each items as it (it.id)}
    <button
      class:on={tool === it.id}
      aria-pressed={tool === it.id}
      aria-label={it.label}
      title={`${it.label} (${it.key})`}
      onclick={() => onpick(it.id)}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d={it.path} />
      </svg>
    </button>
  {/each}
</div>

<style>
  .rail {
    position: absolute; top: 12px; left: 12px; z-index: 15;
    display: flex; flex-direction: column; gap: 2px; padding: 3px;
    background: var(--overlay-bg); backdrop-filter: blur(6px);
    border: 1px solid var(--overlay-line); border-radius: 8px;
    box-shadow: var(--overlay-shadow);
  }
  button {
    width: 32px; height: 32px; padding: 0; display: grid; place-items: center;
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    color: var(--overlay-fg-dim); cursor: pointer;
  }
  button:hover:not(.on) { color: var(--overlay-fg); border-color: transparent; background: var(--overlay-hover); }
  button.on { color: var(--on-accent); background: var(--accent); border-color: var(--accent); }
  svg {
    width: 18px; height: 18px; fill: none;
    stroke: currentColor; stroke-width: 1.8; stroke-linejoin: round; stroke-linecap: round;
  }
  button.on svg { fill: none; }
  @media (prefers-reduced-motion: reduce) { .rail { backdrop-filter: none; } }
</style>
