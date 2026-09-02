<script lang="ts">
  import { dialog } from './dialog';

  let { onclose }: { onclose: () => void } = $props();

  const shortcuts: [string, string][] = [
    ['← / →', 'Immagine precedente / successiva (cartella aperta)'],
    ['F', 'Mostra o nascondi la striscia'],
    ['M', 'Alterna vista termica e mappa'],
    ['Rotella', 'Zoom sul punto del cursore'],
    ['Trascina', 'Sposta la vista (pan)'],
    ['Esc', 'Annulla lo strumento in corso / deseleziona'],
    ['Canc', 'Elimina l’area selezionata'],
    ['Doppio clic o Invio', 'Chiudi il poligono in disegno'],
  ];

  function onKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="backdrop">
  <button type="button" class="scrim" aria-label="Chiudi" onclick={onclose}></button>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Aiuto e scorciatoie" tabindex="-1" use:dialog>
    <header>
      <h2>Aiuto e scorciatoie</h2>
      <button class="x" onclick={onclose} aria-label="Chiudi">×</button>
    </header>
    <div class="body">
      <h3>Cos’è Warmish Web</h3>
      <p>
        Editor per foto termiche radiometriche FLIR. Rimappa la palette, corregge
        i parametri di calibrazione, misura aree e temperature ed esporta le
        immagini pronte — una alla volta, in blocco o per cartelle.
        Tutta l’elaborazione avviene nel browser: nessun file viene caricato
        online. L’unica eccezione è la vista mappa, che scarica le mattonelle
        della cartografia da un provider esterno.
      </p>

      <h3>Scorciatoie da tastiera</h3>
      <table>
        <tbody>
          {#each shortcuts as [key, what] (key)}
            <tr><th>{key}</th><td>{what}</td></tr>
          {/each}
        </tbody>
      </table>

      <h3>Esportazione</h3>
      <p>
        Lo ZIP di una immagine contiene la termica pulita, la termica annotata,
        la foto visibile e — se l’hai attivata — la sovrapposta, più
        <code>aree.csv</code> e la sessione <code>.json</code>.
        «Includi gli originali» aggiunge le foto FLIR di partenza (lo ZIP diventa
        molto più grande, ma il lavoro si riapre ovunque).
      </p>
      <p>
        «Salva sessione» esporta solo il <code>.json</code>: un checkpoint
        leggero che riapri trascinandolo sull’immagine, o sulla cartella. Per
        allineare palette, parametri o aree su più foto usa «Applica
        impostazioni» nella striscia.
      </p>
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
    width: min(520px, 100%); max-height: 100%; display: flex; flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }
  header {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 14px 16px; border-bottom: 1px solid var(--line);
  }
  h2 { font-size: 14px; margin: 0; }
  .x { padding: 2px 9px; font-size: 17px; line-height: 1; }
  .body { padding: 12px 16px 16px; overflow-y: auto; }
  h3 {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted);
    margin: 16px 0 6px;
  }
  h3:first-child { margin-top: 0; }
  p { margin: 0; font-size: 13px; line-height: 1.5; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  tr { border-bottom: 1px solid var(--line); }
  th {
    text-align: left; font-weight: 400; color: var(--accent); padding: 6px 14px 6px 0;
    white-space: nowrap; vertical-align: top; font-variant-numeric: tabular-nums;
  }
  td { padding: 6px 0; color: var(--text); }
</style>
