<script lang="ts">
  import type { ExifEntry } from '../core/exif';
  import type { FlirMetadata } from '../core/flir';
  import { dialog } from './dialog';

  let { exif, metadata, fileName, onclose }: {
    exif: ExifEntry[];
    metadata: FlirMetadata | null;
    fileName: string;
    onclose: () => void;
  } = $props();

  // The FLIR fields are already numbers in memory; show them rounded but honest.
  const flir = $derived<ExifEntry[]>(
    metadata
      ? Object.entries(metadata).map(([tag, v]) => ({
          tag,
          value: typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(4).replace(/\.?0+$/, '') : String(v),
        }))
      : [],
  );

  function onKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="backdrop">
  <button type="button" class="scrim" aria-label="Chiudi" onclick={onclose}></button>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Dati EXIF" tabindex="-1" use:dialog>
    <header>
      <h2>Dati EXIF<span>{fileName}</span></h2>
      <button class="x" onclick={onclose} aria-label="Chiudi">×</button>
    </header>
    <div class="body">
      <h3>EXIF standard</h3>
      {#if exif.length}
        <table>
          <tbody>
            {#each exif as row (row.tag)}
              <tr><th>{row.tag}</th><td>{row.value}</td></tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="hint">Questa immagine non contiene un blocco EXIF standard.</p>
      {/if}

      {#if flir.length}
        <h3>FLIR / Radiometria</h3>
        <table>
          <tbody>
            {#each flir as row (row.tag)}
              <tr><th>{row.tag}</th><td>{row.value}</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; z-index: 50;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }
  .scrim {
    position: absolute; inset: 0; border: 0; border-radius: 0; padding: 0;
    background: rgba(0, 0, 0, 0.6); cursor: default;
  }
  .modal {
    position: relative;
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    width: min(560px, 100%); max-height: 100%; display: flex; flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }
  header {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 14px 16px; border-bottom: 1px solid var(--line);
  }
  h2 { font-size: 14px; margin: 0; display: flex; flex-direction: column; gap: 2px; }
  h2 span { font-size: 11px; color: var(--muted); font-weight: 400; word-break: break-all; }
  .x { padding: 2px 9px; font-size: 17px; line-height: 1; }
  .body { padding: 12px 16px 16px; overflow-y: auto; }
  h3 {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted);
    margin: 14px 0 6px;
  }
  h3:first-child { margin-top: 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  tr { border-bottom: 1px solid var(--line); }
  th {
    text-align: left; font-weight: 400; color: var(--muted); padding: 4px 10px 4px 0;
    white-space: nowrap; vertical-align: top;
  }
  td { padding: 4px 0; text-align: right; font-variant-numeric: tabular-nums; word-break: break-word; }
  .hint { font-size: 12px; color: var(--muted); margin: 0; }
</style>
