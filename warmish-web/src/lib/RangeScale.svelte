<script lang="ts">
  /**
   * DOM colour scale on the right edge of the canvas: palette gradient, a
   * histogram of the frame's temperatures, and two draggable handles for the
   * display window. Dragging a handle switches the range to manual; a
   * double-click (or the "auto" pill) hands it back to auto.
   *
   * This replaces the in-canvas legend the Viewer used to paint — the exported
   * PNGs keep their own legend (`drawLegendH`), untouched.
   */
  interface Props {
    lut: Uint8Array;          // 256 * 3 RGB
    inverted: boolean;
    dataMin: number;          // full data range — histogram domain + drag clamps
    dataMax: number;
    min: number;              // current display window
    max: number;
    histogram: number[];      // bin counts, coldest first
    auto: boolean;            // true unless the window was set by hand
    stretchPct: number;       // 0 = true min/max, >0 = central percentile kept
    folderMode?: boolean;     // window pinned to the whole folder's envelope
    folderAvailable?: boolean; // a folder is open, so the folder scale is offerable
    scanning?: boolean;       // the folder scan is running
    onchange: (min: number, max: number) => void;
    onauto: () => void;       // reset to plain min/max auto (double-click)
    oncycle: () => void;      // advance min/max → 98% → 90% → [folder] → min/max
    onstretch: (pct: number) => void; // set a custom percentile
    onfolder: () => void;     // pin to the common folder scale
  }
  let {
    lut, inverted, dataMin, dataMax, min, max, histogram, auto, stretchPct,
    folderMode = false, folderAvailable = false, scanning = false,
    onchange, onauto, oncycle, onstretch, onfolder,
  }: Props = $props();

  const STRETCH_PRESETS = [90, 95, 98, 99];

  /** Label on the mode pill: MANUALE, AUTO, a percentage, or the folder scale. */
  const modeLabel = $derived(
    scanning ? '…'
    : !auto ? 'manuale'
    : folderMode ? 'cart.'
    : stretchPct > 0 ? `${+stretchPct.toFixed(1)}%`
    : 'auto',
  );
  /** The window clips the histogram's tails — draw guide lines where. */
  const clipped = $derived(auto && (folderMode || stretchPct > 0));

  // Long-press the pill to open the percentile picker; a normal click cycles.
  let pressTimer: ReturnType<typeof setTimeout> | undefined;
  let longPressed = false;
  let showPct = $state(false);

  function pillDown() {
    longPressed = false;
    pressTimer = setTimeout(() => { longPressed = true; showPct = true; }, 450);
  }
  function pillUp() { clearTimeout(pressTimer); }
  function pillClick(e: MouseEvent) {
    e.stopPropagation();
    if (longPressed) { longPressed = false; return; }
    oncycle();
  }

  let trackEl: HTMLDivElement;
  let trackH = $state(1);

  const span = $derived(dataMax - dataMin || 1);
  const eps = $derived(span / 200 || 0.05);

  const gradient = $derived.by(() => {
    const N = 32;
    const stops: string[] = [];
    for (let i = 0; i <= N; i++) {
      const t = i / N;
      let idx = Math.floor((inverted ? 1 - t : t) * 256);
      idx = Math.max(0, Math.min(255, idx));
      stops.push(`rgb(${lut[idx * 3]},${lut[idx * 3 + 1]},${lut[idx * 3 + 2]}) ${(t * 100).toFixed(1)}%`);
    }
    return `linear-gradient(to top, ${stops.join(',')})`;
  });

  const histPath = $derived.by(() => {
    const n = histogram.length;
    if (!n) return '';
    const peak = Math.max(1, ...histogram);
    const pts = histogram.map((c, i) => {
      const y = (1 - (i + 0.5) / n) * 100;
      const x = 100 - (c / peak) * 94;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return `100,0 ${pts.join(' ')} 100,100`;
  });

  /** value -> px from the top of the track */
  const vToY = (v: number) => (1 - (v - dataMin) / span) * trackH;
  const yToV = (y: number) => dataMin + (1 - y / trackH) * span;

  const clamp = (v: number) => Math.max(dataMin, Math.min(dataMax, v));

  let dragging: 'min' | 'max' | null = null;

  function down(which: 'min' | 'max', ev: PointerEvent) {
    dragging = which;
    (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
    ev.preventDefault();
    ev.stopPropagation();
  }
  function moveHandle(ev: PointerEvent) {
    if (!dragging) return;
    const rect = trackEl.getBoundingClientRect();
    const v = clamp(yToV(ev.clientY - rect.top));
    if (dragging === 'min') onchange(Math.min(v, max - eps), max);
    else onchange(min, Math.max(v, min + eps));
  }
  function up(ev: PointerEvent) {
    if (dragging) (ev.currentTarget as HTMLElement).releasePointerCapture?.(ev.pointerId);
    dragging = null;
  }

  function key(which: 'min' | 'max', ev: KeyboardEvent) {
    const step = ev.shiftKey ? 5 : 0.5;
    let d = 0;
    if (ev.key === 'ArrowUp' || ev.key === 'ArrowRight') d = step;
    else if (ev.key === 'ArrowDown' || ev.key === 'ArrowLeft') d = -step;
    else if (ev.key === 'Home') d = -1e9;
    else if (ev.key === 'End') d = 1e9;
    else return;
    ev.preventDefault();
    if (which === 'min') onchange(clamp(Math.min(min + d, max - eps)), max);
    else onchange(min, clamp(Math.max(max + d, min + eps)));
  }

  const fmt = (v: number) => `${v.toFixed(1)}°`;
</script>

<svelte:window onpointerdown={() => (showPct = false)} />

<div class="scale" ondblclick={() => onauto()} role="group" aria-label="Scala e intervallo temperatura">
  <div class="col">
    <div class="modewrap">
      <button
        class="auto"
        class:on={auto}
        onclick={pillClick}
        onpointerdown={(e) => { e.stopPropagation(); pillDown(); }}
        onpointerup={pillUp}
        onpointerleave={pillUp}
        title={
          scanning ? 'Scansione della cartella…'
          : !auto ? 'Intervallo manuale — clic per tornare automatico'
          : folderMode ? 'Scala comune a tutta la cartella — clic per cambiare'
          : stretchPct > 0 ? `Stretch percentile ${modeLabel} — clic per cambiare, tieni premuto per un valore preciso`
          : 'Min/Max reali — clic per lo stretch percentile, tieni premuto per le opzioni'
        }
      >{modeLabel}</button>

      {#if showPct}
        <div
          class="pctpop"
          role="group"
          aria-label="Modalità intervallo automatico"
          onpointerdown={(e) => e.stopPropagation()}
        >
          <span class="pcttitle">Mantieni il {stretchPct > 0 ? +stretchPct.toFixed(1) : 98}% centrale</span>
          <input
            class="pctrange"
            type="range" min="50" max="99.8" step="0.2"
            value={stretchPct > 0 ? stretchPct : 98}
            oninput={(e) => onstretch(+(e.currentTarget as HTMLInputElement).value)}
          />
          <div class="pctpresets">
            {#each STRETCH_PRESETS as p}
              <button class:on={!folderMode && Math.abs(stretchPct - p) < 0.05} onclick={() => onstretch(p)}>{p}%</button>
            {/each}
            <button class:on={!folderMode && stretchPct === 0} onclick={() => { onauto(); showPct = false; }}>reali</button>
          </div>
          {#if folderAvailable}
            <button
              class="pctfolder"
              class:on={folderMode}
              onclick={() => { onfolder(); showPct = false; }}
            >Scala comune alla cartella</button>
          {/if}
        </div>
      {/if}
    </div>

    <div class="track" bind:this={trackEl} bind:clientHeight={trackH}>
      <svg class="hist" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polygon points={histPath} vector-effect="non-scaling-stroke" />
      </svg>
      <div class="bar" style="background:{gradient}"></div>

      <div class="mask top" style="height:{Math.max(0, vToY(max))}px"></div>
      <div class="mask bot" style="height:{Math.max(0, trackH - vToY(min))}px"></div>

      {#if clipped}
        <div class="cut" style="top:{vToY(max)}px"></div>
        <div class="cut" style="top:{vToY(min)}px"></div>
      {/if}

      <div
        class="handle max"
        style="top:{vToY(max)}px"
        role="slider"
        tabindex="0"
        aria-label="Temperatura massima visualizzata"
        aria-valuemin={dataMin}
        aria-valuemax={dataMax}
        aria-valuenow={max}
        aria-valuetext={fmt(max)}
        onpointerdown={(e) => down('max', e)}
        onpointermove={moveHandle}
        onpointerup={up}
        onkeydown={(e) => key('max', e)}
      >
        <span class="lbl">{fmt(max)}</span>
      </div>
      <div
        class="handle min"
        style="top:{vToY(min)}px"
        role="slider"
        tabindex="0"
        aria-label="Temperatura minima visualizzata"
        aria-valuemin={dataMin}
        aria-valuemax={dataMax}
        aria-valuenow={min}
        aria-valuetext={fmt(min)}
        onpointerdown={(e) => down('min', e)}
        onpointermove={moveHandle}
        onpointerup={up}
        onkeydown={(e) => key('min', e)}
      >
        <span class="lbl">{fmt(min)}</span>
      </div>
    </div>
  </div>
</div>

<style>
  .scale {
    position: absolute; top: 16px; right: 16px; z-index: 15;
    height: min(360px, calc(100% - 64px));
    padding: 8px; user-select: none;
    background: var(--overlay-bg); backdrop-filter: blur(6px);
    border: 1px solid var(--overlay-line); border-radius: 8px;
    box-shadow: var(--overlay-shadow);
  }
  .col { display: flex; flex-direction: column; gap: 6px; height: 100%; }
  /* Extra breathing room so the top handle's value label clears the mode pill. */
  .modewrap { position: relative; align-self: flex-end; margin-bottom: 12px; }
  .auto {
    padding: 2px 7px; font-size: 11px; line-height: 1.4;
    text-transform: uppercase; letter-spacing: 0.5px;
    background: transparent; border: 1px solid var(--overlay-line); border-radius: 999px;
    color: var(--overlay-fg-dim); cursor: pointer; touch-action: none;
    font-variant-numeric: tabular-nums;
  }
  .auto.on { color: var(--on-accent); background: var(--accent); border-color: var(--accent); }
  .auto:not(.on):hover { color: var(--overlay-fg); border-color: var(--accent); }

  .pctpop {
    position: absolute; top: calc(100% + 6px); right: 0; z-index: 20;
    display: flex; flex-direction: column; gap: 6px; width: 132px; padding: 8px;
    background: var(--overlay-bg); backdrop-filter: blur(6px);
    border: 1px solid var(--overlay-line); border-radius: 8px; box-shadow: var(--overlay-shadow);
  }
  .pcttitle { font-size: 11px; color: var(--overlay-fg); }
  .pctrange { width: 100%; margin: 0; accent-color: var(--accent); }
  .pctpresets { display: flex; flex-wrap: wrap; gap: 4px; }
  .pctpresets button {
    padding: 1px 5px; font-size: 10px; font-variant-numeric: tabular-nums;
    background: transparent; border: 1px solid var(--overlay-line); border-radius: 999px;
    color: var(--overlay-fg-dim); cursor: pointer;
  }
  .pctpresets button:hover { color: var(--overlay-fg); border-color: var(--accent); }
  .pctpresets button.on { color: var(--on-accent); background: var(--accent); border-color: var(--accent); }
  .pctfolder {
    padding: 3px 6px; font-size: 10.5px; text-align: left;
    background: transparent; border: 1px solid var(--overlay-line); border-radius: var(--radius-sm, 4px);
    color: var(--overlay-fg-dim); cursor: pointer;
  }
  .pctfolder:hover { color: var(--overlay-fg); border-color: var(--accent); }
  .pctfolder.on { color: var(--on-accent); background: var(--accent); border-color: var(--accent); }

  .cut {
    position: absolute; left: 0; right: 0; height: 0;
    border-top: 1px dashed var(--accent); opacity: 0.7; pointer-events: none;
  }

  .track { position: relative; flex: 1; width: 48px; }
  .hist {
    position: absolute; left: 0; top: 0; width: 26px; height: 100%;
    overflow: visible;
  }
  .hist polygon {
    fill: var(--overlay-hist-fill);
    stroke: var(--overlay-hist-line); stroke-width: 1;
  }
  .bar {
    position: absolute; right: 0; top: 0; width: 18px; height: 100%;
    border: 1px solid rgba(0, 0, 0, 0.5); border-radius: 2px;
  }
  .mask {
    position: absolute; right: 0; width: 18px;
    background: var(--overlay-scrim); pointer-events: none;
  }
  .mask.top { top: 0; border-radius: 2px 2px 0 0; }
  .mask.bot { bottom: 0; border-radius: 0 0 2px 2px; }

  .handle {
    position: absolute; right: -3px; width: 30px; height: 0;
    cursor: ns-resize; touch-action: none;
  }
  .handle::before {
    content: ''; position: absolute; right: 0; top: -1px; width: 24px; height: 2px;
    background: var(--overlay-handle); box-shadow: 0 0 0 1px var(--overlay-handle-ring);
  }
  .handle::after {
    content: ''; position: absolute; right: 22px; top: -4px;
    border: 4px solid transparent; border-right-color: var(--overlay-handle);
    filter: drop-shadow(-1px 0 0 var(--overlay-handle-ring));
  }
  .handle:focus-visible { outline: none; }
  .handle:focus-visible::before { background: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
  .lbl {
    position: absolute; right: 30px; top: -8px;
    font-size: 11px; font-variant-numeric: tabular-nums; white-space: nowrap;
    color: var(--overlay-fg); text-shadow: var(--overlay-label-shadow);
  }

  @media (prefers-reduced-motion: reduce) { .scale { backdrop-filter: none; } }
</style>
