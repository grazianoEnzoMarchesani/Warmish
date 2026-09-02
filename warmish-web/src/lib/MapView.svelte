<script lang="ts" module>
  export interface MapPoint {
    /** Stable key — folder-relative path, or the file name for a lone image. */
    path: string;
    name: string;
    lat: number;
    lon: number;
    altitude: number | null;
    direction: number | null;
    directionRef: 'T' | 'M' | null;
    /** Data/blob URL for the popup preview, or null. */
    thumb: string | null;
    /** The image currently open in the thermal viewer. */
    active: boolean;
  }
</script>

<script lang="ts">
  /**
   * Positions GPS-tagged FLIR frames on a slippy map. This is the only part of
   * Warmish that touches the network: the basemap tiles come from Esri or
   * OpenStreetMap, so the area on screen is revealed to that provider. No image
   * or coordinate is uploaded — the notice below says so, once.
   */
  import { onMount } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';

  let { points, onopen }: { points: MapPoint[]; onopen: (path: string) => void } = $props();

  let host: HTMLDivElement;
  let map: L.Map | null = null;
  let markerLayer: L.LayerGroup | null = null;
  let fittedOnce = false;

  const reduceMotion =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  let noticeAck = $state(
    (() => { try { return localStorage.getItem('warmish.mapNoticeAck') === '1'; } catch { return false; } })(),
  );
  function ackNotice() {
    noticeAck = true;
    try { localStorage.setItem('warmish.mapNoticeAck', '1'); } catch { /* private mode */ }
  }

  const BASEMAPS = {
    Satellite: () =>
      L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
          maxZoom: 21,
          maxNativeZoom: 19,
          attribution: 'Tiles &copy; Esri &mdash; Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        },
      ),
    'Mappa stradale': () =>
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }),
  } as const;
  type BasemapName = keyof typeof BASEMAPS;

  function initialBasemap(): BasemapName {
    try {
      const s = localStorage.getItem('warmish.basemap');
      if (s && s in BASEMAPS) return s as BasemapName;
    } catch { /* private mode */ }
    return 'Satellite';
  }

  function coneSvg(dir: number): string {
    // A narrow wedge from the marker centre, pointing "up" then rotated to the
    // compass bearing. overflow is visible so it reaches past the icon box.
    return `<svg class="wm-cone" style="transform:rotate(${dir}deg)" width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><path d="M15 15 L8 -7 L22 -7 Z"/></svg>`;
  }

  function icon(p: MapPoint): L.DivIcon {
    const cone = p.direction !== null ? coneSvg(p.direction) : '';
    return L.divIcon({
      className: 'wm-pin-wrap',
      html: `<div class="wm-pin${p.active ? ' is-active' : ''}">${cone}<span class="wm-dot"></span></div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
      popupAnchor: [0, -14],
    });
  }

  function fmtCoord(lat: number, lon: number): string {
    const ns = lat >= 0 ? 'N' : 'S';
    const ew = lon >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(6)}° ${ns}, ${Math.abs(lon).toFixed(6)}° ${ew}`;
  }

  function popupHtml(p: MapPoint): string {
    const rows: string[] = [];
    rows.push(`<div class="wm-pop-coord">${fmtCoord(p.lat, p.lon)}</div>`);
    const meta: string[] = [];
    if (p.altitude !== null) meta.push(`Quota ${p.altitude.toFixed(0)} m`);
    if (p.direction !== null) {
      meta.push(`Direzione ${p.direction.toFixed(0)}°${p.directionRef === 'M' ? ' (mag.)' : p.directionRef === 'T' ? ' (vero)' : ''}`);
    }
    if (meta.length) rows.push(`<div class="wm-pop-meta">${meta.join(' · ')}</div>`);
    const thumb = p.thumb
      ? `<img class="wm-pop-thumb" src="${p.thumb}" alt="Anteprima di ${escapeHtml(p.name)}" />`
      : '';
    return `<div class="wm-pop">
      ${thumb}
      <div class="wm-pop-name">${escapeHtml(p.name)}</div>
      ${rows.join('')}
      <button type="button" class="wm-pop-open" data-path="${escapeHtml(p.path)}">
        ${p.active ? 'Torna alla vista termica' : 'Apri nel visualizzatore'}
      </button>
    </div>`;
  }

  function escapeHtml(s: string): string {
    return s.replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
  }

  function clusterIcon(n: number, active: boolean): L.DivIcon {
    return L.divIcon({
      className: 'wm-pin-wrap',
      html: `<div class="wm-pin wm-pin--cluster${active ? ' is-active' : ''}"><span class="wm-count">${n}</span></div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      popupAnchor: [0, -16],
    });
  }

  function clusterPopupHtml(items: MapPoint[]): string {
    const list = items
      .map(
        (p) => `<li><button type="button" class="wm-list-open" data-path="${escapeHtml(p.path)}">
          <span class="wm-list-name">${escapeHtml(p.name)}</span>
          ${p.active ? '<span class="wm-list-tag">in vista</span>' : ''}
        </button></li>`,
      )
      .join('');
    // Every GPS-tagged shot at one coordinate: usually a phone/camera that
    // stamps a single cached fix on a whole session, not a real cluster.
    const allHere = items.length === points.length && points.length > 1;
    const note = allHere
      ? `<div class="wm-pop-meta">Tutte le foto con GPS hanno questa stessa coordinata — la fotocamera ha registrato una sola posizione per la sessione, non una per scatto.
         <a class="wm-pop-link" href="geotag/index.html" target="_blank" rel="noopener">Posizionale a mano nel Geotag &rarr;</a></div>`
      : '';
    return `<div class="wm-pop">
      <div class="wm-pop-name">${items.length} scatti in questo punto</div>
      <div class="wm-pop-coord">${fmtCoord(items[0].lat, items[0].lon)}</div>
      ${note}
      <ul class="wm-list">${list}</ul>
    </div>`;
  }

  function renderMarkers(): void {
    if (!map || !markerLayer) return;
    markerLayer.clearLayers();
    if (!points.length) return;

    if (!fittedOnce) {
      fittedOnce = true;
      const ll = points.map((p) => [p.lat, p.lon] as L.LatLngTuple);
      if (ll.length === 1) map.setView(ll[0], 17, { animate: false });
      else map.fitBounds(L.latLngBounds(ll).pad(0.18), { animate: false, maxZoom: 17 });
    }

    // Cluster by on-screen distance at the current zoom: pins that would overlap
    // merge into one counter and split again as you zoom in. FLIR cameras often
    // write the same coarse fix for a whole session, so this is the common case.
    const groups: { items: MapPoint[]; x: number; y: number }[] = [];
    for (const p of points) {
      const pt = map.latLngToContainerPoint([p.lat, p.lon]);
      const g = groups.find((g) => Math.hypot(g.x - pt.x, g.y - pt.y) < 36);
      if (g) g.items.push(p);
      else groups.push({ items: [p], x: pt.x, y: pt.y });
    }

    for (const g of groups) {
      const active = g.items.some((p) => p.active);
      if (g.items.length === 1) {
        const p = g.items[0];
        const m = L.marker([p.lat, p.lon], {
          icon: icon(p), zIndexOffset: p.active ? 1000 : 0, title: p.name, keyboard: true, alt: p.name,
        });
        m.bindPopup(popupHtml(p), { closeButton: true, autoPanPadding: [40, 40] });
        m.on('dblclick', () => onopen(p.path));
        markerLayer.addLayer(m);
      } else {
        const lat = g.items.reduce((s, p) => s + p.lat, 0) / g.items.length;
        const lon = g.items.reduce((s, p) => s + p.lon, 0) / g.items.length;
        const m = L.marker([lat, lon], {
          icon: clusterIcon(g.items.length, active), zIndexOffset: active ? 1000 : 0,
          title: `${g.items.length} scatti`,
        });
        m.bindPopup(clusterPopupHtml(g.items), { closeButton: true, autoPanPadding: [40, 40], minWidth: 200 });
        // Try to spread them by zooming in; a truly co-located set just re-opens the list.
        m.on('dblclick', () => map!.setView([lat, lon], Math.min(map!.getZoom() + 2, 20), { animate: !reduceMotion }));
        markerLayer.addLayer(m);
      }
    }
  }

  onMount(() => {
    map = L.map(host, {
      zoomControl: true,
      attributionControl: true,
      fadeAnimation: !reduceMotion,
      zoomAnimation: !reduceMotion,
      markerZoomAnimation: !reduceMotion,
      worldCopyJump: true,
    });

    const layers = Object.fromEntries(
      (Object.keys(BASEMAPS) as BasemapName[]).map((k) => [k, BASEMAPS[k]()]),
    ) as Record<BasemapName, L.TileLayer>;
    const start = initialBasemap();
    layers[start].addTo(map);
    L.control.layers(layers, {}, { position: 'topright' }).addTo(map);
    map.on('baselayerchange', (e: L.LayersControlEvent) => {
      try { localStorage.setItem('warmish.basemap', e.name); } catch { /* private mode */ }
    });

    markerLayer = L.layerGroup().addTo(map);

    // The popup's action buttons live in Leaflet's DOM, not Svelte's.
    map.on('popupopen', (e: L.PopupEvent) => {
      e.popup.getElement()
        ?.querySelectorAll<HTMLButtonElement>('.wm-pop-open, .wm-list-open')
        .forEach((btn) => btn.addEventListener('click', () => {
          if (btn.dataset.path) onopen(btn.dataset.path);
        }, { once: true }));
    });

    map.on('zoomend resize', renderMarkers);
    renderMarkers();

    const ro = new ResizeObserver(() => map?.invalidateSize());
    ro.observe(host);
    // Container is laid out by now, but a deferred call covers font/layout settle.
    requestAnimationFrame(() => map?.invalidateSize());

    return () => {
      ro.disconnect();
      map?.remove();
      map = null;
      markerLayer = null;
    };
  });

  // Re-place markers when the folder selection or the active image changes.
  $effect(() => {
    void points;
    renderMarkers();
  });
</script>

<div class="wrap">
  <div class="host" bind:this={host}></div>

  {#if !points.length}
    <div class="empty">
      <p>Nessuna coordinata GPS</p>
      <small>Le foto aperte non contengono un tag GPS negli EXIF, quindi non c'&egrave; nulla da posizionare.</small>
      <a class="empty-link" href="geotag/index.html" target="_blank" rel="noopener">Aprile nel Geotag per posizionarle a mano &rarr;</a>
    </div>
  {/if}

  {#if !noticeAck}
    <div class="notice" role="status">
      <p>
        La mappa scarica lo sfondo cartografico da un server esterno
        (Esri&nbsp;/&nbsp;OpenStreetMap). &Egrave; l'unica funzione dell'app che
        si collega a internet: la zona che visualizzi viene rivelata al fornitore
        delle mappe. Nessuna immagine o coordinata lascia il tuo computer.
      </p>
      <button type="button" onclick={ackNotice}>Ho capito</button>
    </div>
  {/if}
</div>

<style>
  .wrap { position: relative; width: 100%; height: 100%; }
  .host {
    width: 100%; height: 100%; background: #0d0f13;
    animation: mapin 0.4s ease both;
  }
  @keyframes mapin { from { opacity: 0; } to { opacity: 1; } }

  .empty {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 8px; text-align: center;
    color: var(--muted); background: var(--bg); pointer-events: none; padding: 24px;
  }
  .empty p { margin: 0; font-size: 15px; }
  .empty small { max-width: 320px; line-height: 1.5; }
  .empty-link {
    pointer-events: auto; margin-top: 4px; font-size: 12.5px;
    color: var(--accent); text-decoration: none;
  }
  .empty-link:hover { text-decoration: underline; }

  .notice {
    position: absolute; left: 12px; bottom: 12px; z-index: 500;
    max-width: min(520px, calc(100% - 24px));
    display: flex; align-items: center; gap: 14px;
    padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px;
    background: rgba(20, 22, 26, 0.94); backdrop-filter: blur(6px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  }
  .notice p { margin: 0; font-size: 12px; line-height: 1.5; color: var(--muted); }
  .notice button { flex: none; padding: 6px 12px; font-size: 12px; }

  @media (prefers-reduced-motion: reduce) {
    .host { animation: none; }
  }

  /* --- Leaflet, themed dark --------------------------------------------- */
  :global(.leaflet-container) {
    background: #0d0f13;
    font: inherit;
    outline: none;
  }
  /* Clear the view-mode switch that floats at the pane's top-left. */
  :global(.leaflet-top.leaflet-left) { top: 44px; }
  :global(.leaflet-bar),
  :global(.leaflet-control-layers) {
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }
  :global(.leaflet-bar a),
  :global(.leaflet-control-layers-toggle) {
    background: var(--panel);
    color: var(--text);
    border-bottom-color: var(--line);
  }
  :global(.leaflet-bar a:hover) { background: #23272f; }
  :global(.leaflet-control-layers-expanded) {
    background: var(--panel);
    color: var(--text);
    padding: 8px 10px;
  }
  :global(.leaflet-control-attribution) {
    background: rgba(20, 22, 26, 0.8);
    color: var(--muted);
  }
  :global(.leaflet-control-attribution a) { color: var(--accent); }

  :global(.leaflet-popup-content-wrapper),
  :global(.leaflet-popup-tip) {
    background: var(--panel) !important;
    color: var(--text) !important;
    border: 1px solid var(--line);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  }
  :global(.leaflet-popup-content) { margin: 10px 12px; font: inherit; color: var(--text); }
  :global(.leaflet-popup-close-button) { color: var(--muted) !important; }

  :global(.wm-pop) { display: grid; gap: 5px; min-width: 190px; }
  :global(.wm-pop-thumb) {
    width: 100%; aspect-ratio: 4 / 3; object-fit: cover;
    border-radius: 5px; border: 1px solid var(--line); background: #000;
  }
  :global(.wm-pop-name) {
    font-size: 12.5px; font-weight: 600; word-break: break-all; color: var(--text);
  }
  :global(.wm-pop-coord) {
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums;
  }
  :global(.wm-pop-meta) { font-size: 11.5px; color: var(--muted); }
  :global(.wm-pop-link) { display: inline-block; margin-top: 4px; color: var(--accent); text-decoration: none; }
  :global(.wm-pop-link:hover) { text-decoration: underline; }
  :global(.wm-pop-open) {
    margin-top: 3px; width: 100%; padding: 6px 10px; font-size: 12px;
    background: var(--accent); color: #101216; border: 0; border-radius: 5px; cursor: pointer;
  }
  :global(.wm-pop-open:hover) { filter: brightness(1.08); }

  :global(.wm-list) {
    list-style: none; margin: 4px 0 0; padding: 0;
    max-height: 190px; overflow-y: auto; display: grid; gap: 3px;
  }
  :global(.wm-list-open) {
    width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 5px 8px; font-size: 12px; text-align: left; cursor: pointer;
    background: var(--bg); border: 1px solid var(--line); border-radius: 4px; color: var(--text);
  }
  :global(.wm-list-open:hover) { border-color: var(--accent); }
  :global(.wm-list-name) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  :global(.wm-list-tag) { flex: none; font-size: 10px; color: var(--accent); }

  /* --- Markers -------------------------------------------------------------- */
  :global(.wm-pin-wrap) { overflow: visible; background: transparent; border: 0; }
  :global(.wm-pin) {
    position: relative; width: 30px; height: 30px;
    display: grid; place-items: center; overflow: visible;
    transition: transform 0.12s ease;
  }
  :global(.wm-pin-wrap:hover .wm-pin) { transform: scale(1.18); z-index: 1000; }
  :global(.wm-dot) {
    width: 13px; height: 13px; border-radius: 50%;
    background: var(--accent); border: 2.5px solid #101216;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
  }
  :global(.wm-pin.is-active .wm-dot) {
    background: #fff; box-shadow: 0 0 0 3px var(--accent), 0 1px 4px rgba(0, 0, 0, 0.6);
  }
  :global(.wm-cone) {
    position: absolute; left: 0; top: 0; overflow: visible;
    transform-origin: 15px 15px; pointer-events: none;
  }
  :global(.wm-cone path) { fill: color-mix(in srgb, var(--accent) 42%, transparent); }
  :global(.wm-pin.is-active .wm-cone path) { fill: color-mix(in srgb, var(--accent) 62%, transparent); }

  :global(.wm-pin--cluster) {
    width: 32px; height: 32px; border-radius: 50%;
    background: var(--accent); border: 2.5px solid #101216;
    color: #101216; font-size: 12px; font-weight: 700;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.6);
  }
  :global(.wm-pin--cluster.is-active) {
    box-shadow: 0 0 0 3px var(--accent), 0 1px 6px rgba(0, 0, 0, 0.6);
  }
  :global(.wm-count) { line-height: 1; font-variant-numeric: tabular-nums; }

  :global(.wm-pin.is-active::before) {
    content: ''; position: absolute; width: 30px; height: 30px; border-radius: 50%;
    border: 2px solid var(--accent); animation: wmpulse 2s ease-out infinite;
  }
  @keyframes wmpulse {
    0% { transform: scale(0.5); opacity: 0.9; }
    100% { transform: scale(1.9); opacity: 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    :global(.wm-pin.is-active::before) { animation: none; opacity: 0; }
    :global(.wm-pin) { transition: none; }
  }
</style>
