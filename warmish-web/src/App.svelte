<script lang="ts">
  import { untrack, tick } from 'svelte';
  import Viewer from './lib/Viewer.svelte';
  import ExifModal from './lib/ExifModal.svelte';
  import HelpModal from './lib/HelpModal.svelte';
  import ToolRail from './lib/ToolRail.svelte';
  import RangeScale from './lib/RangeScale.svelte';
  import Toasts from './lib/Toasts.svelte';
  import { toast, progressToast } from './lib/toast.svelte';
  import { dialog } from './lib/dialog';
  import MapView, { type MapPoint } from './lib/MapView.svelte';
  import type { Tool } from './lib/tools';
  import { parseThermalImage, type ThermalFile } from './core/flir';
  import { parseCapture, parseExif, parseGps, type ExifEntry, type GpsFix } from './core/exif';
  import { computeTemperatures, parametersFromMetadata, percentileRange, temperatureRange, type ThermalParameters } from './core/planck';
  import { PALETTE_NAMES, DEFAULT_PALETTE, colorize, getLut } from './core/colormap';
  import {
    BLEND_NAMES, composite, imageDataToCanvas, alignmentFromMetadata,
    DEFAULT_ALIGNMENT, type BlendMode, type OverlayAlignment,
  } from './core/render';
  import {
    FILTERS, DEFAULT_FILTER, applyVisibleFilter, filterPreset, isIdentityFilter,
    type VisibleFilter, type FilterName,
  } from './core/imageFilter';
  import {
    roiColor, roiStatistics, type Roi, type RoiStats,
  } from './core/roi';
  import { DEFAULT_LABEL_SETTINGS, type RoiLabelSettings } from './core/roiRender';
  import { buildSession, parseSession, type SessionPatch } from './core/session';
  import { renderHeroImage, type RenderSettings, type UserParameters } from './core/pipeline';
  import type { BatchMessage, BatchRequest } from './lib/batch.worker';

  const APP_VERSION = '1.0.0';

  let file = $state<ThermalFile | null>(null);
  let fileName = $state('');
  // The undecoded source of the open image, kept so "Esporta (.zip)" can bundle
  // it and re-run the pipeline on the exact bytes the camera wrote.
  let currentFile = $state.raw<File | null>(null);
  let exif = $state<ExifEntry[]>([]);
  let showExif = $state(false);
  let showHelp = $state(false);
  // "Apri" dropdown in the top bar.
  let openMenu = $state(false);

  // Theme: follow the OS ('auto') or pin light/dark. Stamped on <html> for app.css.
  type Theme = 'auto' | 'light' | 'dark';
  let theme = $state<Theme>(
    (() => { try { return (localStorage.getItem('warmish.theme') as Theme) || 'auto'; } catch { return 'auto'; } })(),
  );
  $effect(() => {
    const el = document.documentElement;
    if (theme === 'auto') el.removeAttribute('data-theme');
    else el.setAttribute('data-theme', theme);
    try { localStorage.setItem('warmish.theme', theme); } catch { /* private mode */ }
  });
  const THEME_LABEL: Record<Theme, string> = { auto: 'automatico', light: 'chiaro', dark: 'scuro' };
  const THEME_GLYPH: Record<Theme, string> = { auto: '◐', light: '☀', dark: '☾' };
  const cycleTheme = () => {
    theme = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
  };
  // Current zoom %, reported by the viewer, shown in the status bar.
  let zoomPct = $state(100);
  let busy = $state(false);

  let params = $state<ThermalParameters | null>(null);
  let objectDistance = $state(1);
  let palette = $state<string>(DEFAULT_PALETTE);
  let inverted = $state(false);
  let blend = $state<BlendMode>('Normal');
  let opacity = $state(1);
  let showVisible = $state(false);
  let showLegend = $state(true);
  let autoRange = $state(true);
  // Auto-range stretch: 0 keeps the true min/max at the ends of the scale; >0
  // clips to that central percentile of the pixels, so a lone hot/cold pixel
  // can't flatten the contrast. Only meaningful while `autoRange` is on.
  let stretchPct = $state(0);
  // "Common folder scale": an override layer (does not touch autoRange/stretch/
  // manual) that pins the window to the min-of-mins / max-of-maxes across every
  // image in the open folder, so frames can be compared at a glance. The bounds
  // are scanned lazily — see `scanFolderRange`.
  let folderRange = $state(false);
  let folderBounds = $state<{ min: number; max: number } | null>(null);
  let folderRangeScanning = $state(false);

  function cycleRange() {
    if (!autoRange) { autoRange = true; folderRange = false; stretchPct = 0; return; }
    if (folderRange) { folderRange = false; stretchPct = 0; return; }
    const steps: (number | 'folder')[] = folder.length ? [0, 98, 90, 'folder'] : [0, 98, 90];
    const next = steps[(steps.indexOf(stretchPct) + 1) % steps.length];
    if (next === 'folder') { folderRange = true; stretchPct = 0; scanFolderRange(); }
    else stretchPct = next;
  }
  function setStretch(pct: number) {
    autoRange = true;
    folderRange = false;
    stretchPct = Math.min(99.8, Math.max(0, pct));
  }
  function enableFolderRange() {
    autoRange = true;
    stretchPct = 0;
    folderRange = true;
    scanFolderRange();
  }
  function resetRange() {
    autoRange = true;
    folderRange = false;
    stretchPct = 0;
  }
  let manualMin = $state(0);
  let manualMax = $state(100);
  let alignment = $state<OverlayAlignment>({ ...DEFAULT_ALIGNMENT });
  let visibleFilter = $state<VisibleFilter>({ ...DEFAULT_FILTER });

  let rois = $state<Roi[]>([]);
  let selectedId = $state<string | null>(null);
  let tool = $state<Tool>('pan');
  let labels = $state<RoiLabelSettings>({ ...DEFAULT_LABEL_SETTINGS });
  let roiCounter = 0;

  // Sidebar is split into task-focused tabs so only one group of controls is on
  // screen at a time; the choice is remembered like the filmstrip.
  type TabId = 'immagine' | 'aree' | 'esporta';
  const TAB_LABELS: [TabId, string][] = [
    ['immagine', 'Immagine'], ['aree', 'Aree'], ['esporta', 'Esporta'],
  ];
  const TABS: TabId[] = TAB_LABELS.map(([id]) => id);

  async function onTabKey(ev: KeyboardEvent) {
    const i = TABS.indexOf(activeTab);
    let j = i;
    if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') j = (i + 1) % TABS.length;
    else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp') j = (i - 1 + TABS.length) % TABS.length;
    else if (ev.key === 'Home') j = 0;
    else if (ev.key === 'End') j = TABS.length - 1;
    else return;
    ev.preventDefault();
    activeTab = TABS[j];
    await tick();
    (ev.currentTarget as HTMLElement).parentElement
      ?.querySelector<HTMLElement>('[role="tab"][tabindex="0"]')?.focus();
  }
  let activeTab = $state<TabId>(
    (() => {
      try {
        const t = localStorage.getItem('warmish.tab') as TabId;
        return TABS.includes(t) ? t : 'immagine';
      } catch { return 'immagine'; }
    })(),
  );
  $effect(() => {
    try { localStorage.setItem('warmish.tab', activeTab); } catch { /* private mode */ }
  });

  // The bulk-edit slide-over (folder view). Selection itself stays on the strip.
  let bulkOpen = $state(false);

  // "Avanzate" disclosure in the Immagine tab — calibration, filter, alignment.
  let advOpen = $state(
    (() => { try { return localStorage.getItem('warmish.adv') === '1'; } catch { return false; } })(),
  );
  $effect(() => {
    try { localStorage.setItem('warmish.adv', advOpen ? '1' : '0'); } catch { /* private mode */ }
  });

  let visibleBitmap = $state<ImageBitmap | null>(null);
  let probe = $state<{ x: number; y: number; t: number } | null>(null);
  let viewer = $state<Viewer | null>(null);

  // --- Map view -------------------------------------------------------------
  // GPS fix of the image on screen, plus (for a folder) a fix per file, scanned
  // lazily the first time the map is opened. `viewMode` swaps the thermal canvas
  // for the map without unmounting the viewer, so its pan/zoom survives.
  let gps = $state<GpsFix | null>(null);
  let viewMode = $state<'thermal' | 'map'>('thermal');
  let folderGps = $state(new Map<string, GpsFix>());
  /** Capture time per folder path, ms epoch — orders the map tour. */
  let folderTime = $state(new Map<string, number>());
  let folderGpsScanned = $state(false);
  let folderGpsScanning = $state(false);
  let currentThumb = $state<string | null>(null);

  /** "YYYY-MM-DD HH:MM:SS" (naive local) → ms epoch, or null. */
  function captureMs(bytes: Uint8Array): number | null {
    const dt = parseCapture(bytes).datetime;
    if (!dt) return null;
    const ms = Date.parse(dt.replace(' ', 'T'));
    return Number.isNaN(ms) ? null : ms;
  }

  async function scanFolderGps() {
    if (!folder.length || folderGpsScanned || folderGpsScanning) return;
    folderGpsScanning = true;
    try {
      const next = new Map<string, GpsFix>();
      const times = new Map<string, number>();
      for (const e of folder) {
        try {
          // The standard Exif APP1 sits at the head of the file, before the bulky
          // FLIR blocks — 256 kB is a generous margin, and avoids reading GBs.
          const head = new Uint8Array(await e.file.slice(0, 262144).arrayBuffer());
          const fix = parseGps(head);
          if (fix) next.set(e.path, fix);
          const t = captureMs(head);
          if (t !== null) times.set(e.path, t);
        } catch { /* unreadable file — skip */ }
      }
      folderGps = next;
      folderTime = times;
      folderGpsScanned = true;
    } finally {
      folderGpsScanning = false;
    }
  }

  /**
   * Scan every folder image for its own data range and keep the global envelope
   * (min of mins, max of maxes) in `folderBounds`. Heavy — a full radiometric
   * decode per file — so it runs once, lazily, when the "common folder scale"
   * mode is turned on, and is re-run only when a bulk edit changes calibration.
   * Each image is measured against its own embedded parameters plus whatever its
   * saved session overrides, matching how the filmstrip renders it.
   */
  async function scanFolderRange() {
    if (!folder.length || folderBounds || folderRangeScanning) return;
    folderRangeScanning = true;
    const prog = progressToast('Scansione della cartella per la scala comune…');
    try {
      let lo = Infinity;
      let hi = -Infinity;
      let done = 0;
      for (const e of folder) {
        try {
          const parsed = await parseCached(e);
          const p = parametersFromMetadata(parsed.metadata);
          const saved = folderState.get(e.path);
          if (saved) {
            const patch = parseSession(saved);
            if (patch.parameters) Object.assign(p, patch.parameters);
          }
          const r = temperatureRange(computeTemperatures(parsed.raw, p));
          if (r.min < lo) lo = r.min;
          if (r.max > hi) hi = r.max;
        } catch { /* unreadable frame — skip it */ }
        prog.update(++done, folder.length, `${done}/${folder.length}`);
      }
      if (lo < hi) {
        folderBounds = { min: lo, max: hi };
        prog.finish('success', `Scala comune alla cartella: ${lo.toFixed(1)}–${hi.toFixed(1)} °C`);
        if (folderRange) regenThumbs(folder.map((e) => e.path));
      } else {
        folderRange = false;
        prog.finish('error', 'Impossibile calcolare la scala comune alla cartella');
      }
    } finally {
      folderRangeScanning = false;
    }
  }

  /**
   * A small JPEG of the current image for the map popup. The thermal layer is
   * always composited over the embedded photo when the file carries one, so the
   * open image's preview matches the folder previews regardless of whether
   * "Sovrapponi" is toggled on in the viewer. The visible-photo *filter* is left
   * off on purpose: pixel effects like halftone and dithering only read at 100 %,
   * and turn to mush at thumbnail size.
   */
  function thumbDataUrl(maxWidth?: number): string | null {
    try {
      if (!file || !thermalCanvas) return null;
      const vis = visibleBitmap as (CanvasImageSource & { width: number; height: number }) | null;
      let c = composite({
        thermal: thermalCanvas, width: file.width, height: file.height,
        visible: vis, blend, opacity, alignment,
      }).canvas as HTMLCanvasElement;
      if (maxWidth && c.width > maxWidth) c = downscale(c, maxWidth);
      return 'toDataURL' in c ? c.toDataURL('image/jpeg', 0.72) : null;
    } catch { return null; }
  }

  /** A fresh canvas holding `src` scaled to `w` px wide, aspect preserved. */
  function downscale(
    src: CanvasImageSource & { width: number; height: number },
    w: number,
  ): HTMLCanvasElement {
    const h = Math.max(1, Math.round((w * src.height) / src.width));
    const out = document.createElement('canvas');
    out.width = w;
    out.height = h;
    out.getContext('2d')!.drawImage(src as CanvasImageSource, 0, 0, w, h);
    return out;
  }

  /** True while MapView is running its cinematic tour — the shell hides its
   *  chrome (sidebar, filmstrip, top and status bars) to give the map the room. */
  let tourMode = $state(false);

  function setViewMode(mode: 'thermal' | 'map') {
    if (mode !== 'map') tourMode = false;
    viewMode = mode;
    if (mode === 'map') {
      currentThumb = thumbDataUrl();
      scanFolderGps();
    }
  }

  /** Capture time of the single open image, ms epoch — from its parsed EXIF. */
  const loneTime = $derived.by<number | null>(() => {
    const raw = exif.find((e) => e.tag === 'DateTimeOriginal' || e.tag === 'DateTime')?.value;
    if (!raw) return null;
    const ms = Date.parse(raw.replace(/^(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3').replace(' ', 'T'));
    return Number.isNaN(ms) ? null : ms;
  });

  /** Marker set for the map: the whole folder when one is open, else this image. */
  const mapPoints = $derived.by<MapPoint[]>(() => {
    const pts: MapPoint[] = [];
    if (folder.length) {
      for (const e of folder) {
        const fix = e.path === activePath && gps ? gps : folderGps.get(e.path);
        if (!fix) continue;
        pts.push({
          path: e.path,
          name: e.path.split('/').pop() ?? e.path,
          lat: fix.lat, lon: fix.lon, altitude: fix.altitude,
          direction: fix.direction, directionRef: fix.directionRef,
          thumb: e.path === activePath ? currentThumb ?? e.thumb : e.thumb,
          active: e.path === activePath,
          time: e.path === activePath && loneTime !== null ? loneTime : folderTime.get(e.path) ?? null,
        });
      }
    } else if (gps && fileName) {
      pts.push({
        path: fileName, name: fileName,
        lat: gps.lat, lon: gps.lon, altitude: gps.altitude,
        direction: gps.direction, directionRef: gps.directionRef,
        thumb: currentThumb, active: true, time: loneTime,
      });
    }
    return pts;
  });

  const mapCount = $derived(
    folder.length
      ? (folderGpsScanned ? mapPoints.length : (gps ? 1 : 0))
      : (gps ? 1 : 0),
  );

  function openFromMap(path: string) {
    setViewMode('thermal');
    if (folder.length && path !== activePath) openFromFolder(path);
  }

  const temperatures = $derived(file && params ? computeTemperatures(file.raw, params) : null);
  const dataRange = $derived(temperatures ? temperatureRange(temperatures) : { min: 0, max: 0 });
  /** Auto window: the full data range, or its central-percentile stretch. */
  const autoBounds = $derived(
    temperatures && stretchPct > 0 ? percentileRange(temperatures, stretchPct) : dataRange,
  );
  /** True while the common folder scale is chosen and its bounds are known. */
  const folderScaleActive = $derived(autoRange && folderRange && folderBounds !== null);
  const range = $derived.by(() => {
    if (!autoRange) return { min: manualMin, max: manualMax };
    if (folderScaleActive) return folderBounds!;
    return autoBounds;
  });

  /**
   * Domain of the range scale. Normally this image's own min/max; under the
   * common folder scale it widens to also contain the folder envelope, so the
   * handles stay on the track and you can see where this frame sits within it.
   */
  const scaleDomain = $derived.by(() => {
    if (folderScaleActive) {
      return {
        min: Math.min(dataRange.min, folderBounds!.min),
        max: Math.max(dataRange.max, folderBounds!.max),
      };
    }
    return dataRange;
  });

  /** Temperature distribution over the scale domain — behind the range scale. */
  const HIST_BINS = 48;
  const histogram = $derived.by(() => {
    const t = temperatures;
    if (!t) return [];
    const lo = scaleDomain.min;
    const span = scaleDomain.max - scaleDomain.min || 1;
    const bins = new Array<number>(HIST_BINS).fill(0);
    for (let i = 0; i < t.length; i++) {
      const v = t[i];
      if (Number.isNaN(v)) continue;
      let b = Math.floor(((v - lo) / span) * HIST_BINS);
      if (b < 0) b = 0; else if (b >= HIST_BINS) b = HIST_BINS - 1;
      bins[b]++;
    }
    return bins;
  });

  const thermalCanvas = $derived.by(() => {
    if (!file || !temperatures) return null;
    const px = colorize(temperatures, { palette, inverted, min: range.min, max: range.max });
    return imageDataToCanvas(px, file.width, file.height);
  });

  /**
   * The visible photo with its filter baked in. Recomputed only when the source
   * bitmap or the filter changes — not on every palette/opacity tweak — so a
   * heavy filter (Sobel, halftone) runs at most once per adjustment.
   */
  const filteredVisible = $derived.by(() => {
    if (!showVisible || !visibleBitmap) return null;
    if (isIdentityFilter(visibleFilter)) return visibleBitmap as CanvasImageSource & { width: number; height: number };
    return applyVisibleFilter(visibleBitmap, visibleFilter) as CanvasImageSource & { width: number; height: number };
  });

  const view = $derived.by(() => {
    if (!file || !thermalCanvas) return null;
    return composite({
      thermal: thermalCanvas,
      width: file.width,
      height: file.height,
      visible: filteredVisible,
      blend,
      opacity,
      alignment,
    });
  });

  /** Per-ROI statistics, recomputed from raw counts with each ROI's own emissivity. */
  const roiStats = $derived.by(() => {
    const out = new Map<string, RoiStats | null>();
    if (!file || !params) return out;
    for (const roi of rois) out.set(roi.id, roiStatistics(roi, file.raw, file.width, file.height, params));
    return out;
  });

  const selected = $derived(rois.find((r) => r.id === selectedId) ?? null);

  const stats = $derived.by(() => {
    if (!temperatures) return null;
    let sum = 0;
    let n = 0;
    for (let i = 0; i < temperatures.length; i++) {
      const v = temperatures[i];
      if (!Number.isNaN(v)) { sum += v; n++; }
    }
    return { min: dataRange.min, max: dataRange.max, mean: n ? sum / n : 0, pixels: temperatures.length };
  });

  async function load(f: File) {
    busy = true;
    try {
      const bytes = new Uint8Array(await f.arrayBuffer());
      const parsed = parseThermalImage(bytes);
      exif = parseExif(bytes);
      gps = parseGps(bytes);
      visibleBitmap?.close();
      visibleBitmap = parsed.visible
        ? await createImageBitmap(new Blob([parsed.visible as BlobPart], { type: 'image/jpeg' }))
        : null;
      file = parsed;
      fileName = f.name;
      currentFile = f;
      params = parametersFromMetadata(parsed.metadata);
      objectDistance = parsed.metadata.ObjectDistance;
      const r = temperatureRange(computeTemperatures(parsed.raw, params));
      manualMin = Math.round(r.min * 10) / 10;
      manualMax = Math.round(r.max * 10) / 10;
      showVisible = parsed.visible !== null && showVisible;
      rois = [];
      selectedId = null;
      roiCounter = 0;
      // Start from the camera's own thermal/visible registration; the user can
      // still nudge it, and "Reimposta allineamento" returns here.
      alignment = alignmentFromMetadata(parsed.metadata);
    } catch (e) {
      file = null;
      params = null;
      exif = [];
      gps = null;
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      busy = false;
    }
  }

  /** Applies a sidecar on top of the currently open image. `announce` is off for
   *  the silent restore that happens on every folder-navigation step. */
  function applySession(patch: SessionPatch, source: string, announce = true) {
    if (params && patch.parameters) Object.assign(params, patch.parameters);
    if (patch.objectDistance !== undefined) objectDistance = patch.objectDistance;
    if (patch.palette !== undefined) palette = patch.palette;
    if (patch.inverted !== undefined) inverted = patch.inverted;
    if (patch.autoRange !== undefined) autoRange = patch.autoRange;
    if (patch.stretchPct !== undefined) stretchPct = patch.stretchPct;
    if (patch.manualMin !== undefined) manualMin = patch.manualMin;
    if (patch.manualMax !== undefined) manualMax = patch.manualMax;
    if (patch.blend !== undefined) blend = patch.blend;
    if (patch.opacity !== undefined) opacity = patch.opacity;
    if (patch.alignment !== undefined) alignment = patch.alignment;
    if (patch.visibleFilter !== undefined) visibleFilter = patch.visibleFilter;
    if (patch.labels !== undefined) labels = patch.labels;
    if (patch.rois !== undefined) {
      rois = patch.rois;
      roiCounter = rois.length;
      selectedId = null;
      // The overlay is only worth showing if the session actually configured one.
      if (visibleBitmap && (patch.alignment || patch.blend)) showVisible = true;
    }
    if (announce) toast.success(`Sessione caricata da ${source}`);
  }

  async function loadSession(f: File) {
    try {
      applySession(parseSession(JSON.parse(await f.text())), f.name);
    } catch (e) {
      toast.error(`Sessione non valida: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  /** Accepts an image, a session, or both at once — the resume flow from the plan. */
  async function handleFiles(list: FileList | File[]) {
    const files = Array.from(list);
    const images = files.filter((f) => /\.jpe?g$/i.test(f.name));
    const image = images[0];
    const session = files.find((f) => /\.json$/i.test(f.name));

    // A lone folder-session file merges into the folder already open.
    if (session && !image && folder.length) {
      try {
        const obj = JSON.parse(await session.text());
        if (obj?.warmish_folder_session != null && obj.files) {
          const merged = new Map(folderState);
          const paths = new Map(folder.map((e) => [fileBase(e.path), e.path]));
          for (const [k, v] of Object.entries(obj.files)) {
            const path = paths.get(fileBase(k)) ?? k;
            merged.set(path, v as Record<string, unknown>);
          }
          folderState = merged;
          const active = applyWorkspace(obj.workspace) ?? activePath;
          activePath = null;
          if (active) await openFromFolder(active);
          toast.success(`Sessione cartella caricata (${Object.keys(obj.files).length} immagini)`);
          return;
        }
      } catch { /* fall through to the normal error */ }
    }

    // Several images at once — dropped or multi-selected — open as a folder, the
    // same filmstrip + bulk-edit workflow as picking a directory. This is the
    // only multi-file path, so a loose set from anywhere still gets one zip.
    if (images.length > 1) { await ingestFolder(files); return; }

    if (image) await load(image);
    if (session && file) await loadSession(session);
    else if (session && !image) toast.error('Apri prima l’immagine, poi la sessione .json');
  }

  function onPick(ev: Event) {
    const list = (ev.target as HTMLInputElement).files;
    if (list?.length) handleFiles(list);
  }

  function onDrop(ev: DragEvent) {
    ev.preventDefault();
    if (ev.dataTransfer?.files.length) handleFiles(ev.dataTransfer.files);
  }

  function onProbe(x: number, y: number) {
    if (!file || !temperatures || x < 0 || y < 0 || x >= file.width || y >= file.height) {
      probe = null;
      return;
    }
    probe = { x, y, t: temperatures[y * file.width + x] };
  }

  function addRoi(roi: Roi) {
    roiCounter++;
    const prefix = roi.type === 'SpotROI' ? 'Spot' : roi.type === 'PolygonROI' ? 'Polygon' : 'Rectangle';
    rois = [...rois, { ...roi, name: roi.name || `${prefix}_${roiCounter}`, color: roiColor(rois.length) }];
    selectedId = rois[rois.length - 1].id;
  }

  function deleteRoi(id: string) {
    rois = rois.filter((r) => r.id !== id);
    if (selectedId === id) selectedId = null;
  }

  function download(blob: Blob, name: string) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const baseName = $derived(fileName.replace(/\.[^.]+$/, ''));

  /** The full session object for whatever image is open right now. */
  function snapshotSession(): Record<string, unknown> | null {
    if (!params) return null;
    return buildSession({
      parameters: params, objectDistance, palette, inverted, autoRange, stretchPct, manualMin, manualMax,
      showVisible, blend, opacity, alignment, visibleFilter, labels, rois,
    });
  }

  function exportSession() {
    const data = snapshotSession();
    if (!data) return;
    download(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), `${baseName}.json`);
  }

  /**
   * The whole folder as one lightweight `.json` — every image's edit state keyed
   * by file name, plus where you left off. It's the checkpoint counterpart of the
   * `originali/` kit: no rasters, reopens by re-picking the folder and dropping
   * this file. Read back by `ingestFolder` and `handleFiles` via the
   * `warmish_folder_session` shape the desktop also writes.
   */
  function exportFolderSession() {
    if (!folder.length) return;
    if (activePath) {
      const s = snapshotSession();
      if (s) remember(activePath, s);
    }
    const files: Record<string, unknown> = {};
    for (const e of folder) {
      const s = folderState.get(e.path);
      if (s) files[e.path] = s; // full relative path, as the desktop keys it
    }
    const obj = {
      warmish_folder_session: '1.0',
      files,
      // Warmish-web extension; the desktop ignores unknown keys.
      workspace: {
        active: activePath,
        selection: [...selection],
        include_originals: includeOriginals,
        area_mode: areaMode,
        folder_range: folderRange,
      },
    };
    const date = new Date().toISOString().slice(0, 10);
    download(
      new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }),
      `warmish_sessione_cartella_${date}.json`,
    );
  }

  /**
   * Apply a folder-session `workspace` block: sets selection, options and page,
   * and returns the folder path to reopen (or `null`). Silently ignores anything
   * missing or unrecognised. The caller owns the reopen, since the surrounding
   * `activePath` handling differs between the two import paths.
   */
  function applyWorkspace(ws: unknown): string | null {
    if (!ws || typeof ws !== 'object') return null;
    const w = ws as Record<string, any>;
    // Match a saved key to a current folder entry: exact relative path first, then
    // bare file name, so the session survives a folder rename or re-export.
    const byPath = new Set(folder.map((e) => e.path));
    const byBase = new Map(folder.map((e) => [fileBase(e.path), e.path]));
    const resolve = (n: unknown): string | undefined => {
      const s = String(n);
      return byPath.has(s) ? s : byBase.get(fileBase(s));
    };
    if (Array.isArray(w.selection)) {
      selection = new Set(w.selection.map(resolve).filter((p): p is string => !!p));
    }
    if (typeof w.include_originals === 'boolean') includeOriginals = w.include_originals;
    if (w.area_mode === 'none' || w.area_mode === 'appearance' || w.area_mode === 'replace') {
      areaMode = w.area_mode;
    }
    if (w.folder_range === true) { folderRange = true; folderBounds = null; }
    const active = w.active != null ? resolve(w.active) : undefined;
    if (active) page = Math.max(0, Math.floor(folder.findIndex((e) => e.path === active) / PAGE));
    return active ?? null;
  }

  /**
   * The range fields for an export. The common folder scale is a live override
   * layer, so it is baked here into a fixed manual window — the worker renders
   * one image at a time and cannot see the rest of the folder.
   */
  function rangeSettings(): Pick<RenderSettings, 'autoRange' | 'stretchPct' | 'manualMin' | 'manualMax'> {
    if (folderScaleActive) {
      return { autoRange: false, stretchPct: 0, manualMin: folderBounds!.min, manualMax: folderBounds!.max };
    }
    return { autoRange, stretchPct, manualMin, manualMax };
  }

  /** Render settings for the open image, with the on-screen parameters baked in. */
  function currentSettings(): RenderSettings {
    return {
      palette, inverted, ...rangeSettings(), showVisible, blend, opacity,
      alignment: { ...alignment },
      visibleFilter: { ...visibleFilter },
      labels: { ...labels },
      rois: rois.map((r) => $state.snapshot(r) as Roi),
      parameters: params
        ? {
            Emissivity: params.Emissivity,
            ReflectedApparentTemperature: params.ReflectedApparentTemperature,
            AtmosphericTemperature: params.AtmosphericTemperature,
            AtmosphericTransmission: params.AtmosphericTransmission,
            RelativeHumidity: params.RelativeHumidity,
          }
        : null,
    };
  }

  /** The open image as a one-item export zip — same structure as the batch. */
  async function exportZip() {
    if (!currentFile || batchProgress) return;
    if (folderRange && !folderBounds) await scanFolderRange();
    dispatchExport([currentFile], currentSettings(), undefined, includeOriginals);
  }

  // --- Folder ----------------------------------------------------------------
  // Open a whole directory, page through it in the filmstrip, and never lose the
  // edits made on an image when you move to the next one. The per-image edit
  // state is a tiny session object kept in memory for every image; the decoded
  // raster is only ever the one on screen, re-decoded on the way back.
  type FolderEntry = { file: File; path: string; thumb: string };
  const PAGE = 60;
  let folder = $state.raw<FolderEntry[]>([]);
  let folderState = $state(new Map<string, Record<string, unknown>>());
  let activePath = $state<string | null>(null);
  let page = $state(0);
  let filmstripOpen = $state(
    (() => { try { return localStorage.getItem('warmish.filmstrip') !== '0'; } catch { return true; } })(),
  );

  const relPath = (f: File) => (f as any).webkitRelativePath || f.name;
  // ponytail: copy-on-write so the {#each} dot reacts; fine for a few thousand
  // tiny entries, revisit only if a folder that large ever feels sluggish.
  const remember = (path: string, s: Record<string, unknown>) => {
    folderState = new Map(folderState).set(path, s);
  };
  const stripExt = (s: string) => s.replace(/\.[^.]+$/, '');
  const fileBase = (s: string) => s.slice(s.lastIndexOf('/') + 1);
  const pageCount = $derived(Math.max(1, Math.ceil(folder.length / PAGE)));
  const pageEntries = $derived(folder.slice(page * PAGE, page * PAGE + PAGE));

  // --- Filmstrip selection --------------------------------------------------
  // Which folder images the bulk actions apply to. Ephemeral; copy-on-write so
  // the {#each} and the derived count react, same idiom as `folderState`.
  let selection = $state(new Set<string>());
  const selectedCount = $derived(selection.size);

  function toggleSelect(path: string) {
    const s = new Set(selection);
    if (s.has(path)) s.delete(path); else s.add(path);
    selection = s;
  }
  const selectAll = () => { selection = new Set(folder.map((e) => e.path)); };
  const selectNone = () => { selection = new Set(); };
  const invertSelection = () => {
    selection = new Set(folder.filter((e) => !selection.has(e.path)).map((e) => e.path));
  };

  /**
   * Copy the open image's settings onto every selected image — palette, range,
   * thermal parameters, overlay alignment and labels are always copied. The
   * areas have three possible intents, so they get their own choice:
   *   • 'none'       — leave each image's areas exactly as they are;
   *   • 'appearance' — keep every image's own areas and geometry, but align the
   *                    colour and emissivity of any area whose name matches one
   *                    on the current image (join key = trimmed name; names that
   *                    aren't unique on the current image are skipped);
   *   • 'replace'    — overwrite the target areas with a copy of the current
   *                    ones, positions included (same-scene time-lapse case).
   */
  type AreaMode = 'none' | 'appearance' | 'replace';
  let areaMode = $state<AreaMode>('none');

  function applyToSelected() {
    if (!activePath || selection.size === 0) return;
    const cur = snapshotSession();
    if (!cur) return;
    remember(activePath, cur);
    const { rois: curRoisRaw, ...shared } = cur;
    const curRois = (curRoisRaw as Array<Record<string, unknown>>) ?? [];

    // 'appearance': a trimmed-name → {color, emissivity} lookup built only from
    // names that occur exactly once on the current image. Ambiguous names are
    // collected so the notice can name what it skipped.
    const seen = new Map<string, number>();
    for (const r of curRois) {
      const k = String(r.name ?? '').trim();
      if (k) seen.set(k, (seen.get(k) ?? 0) + 1);
    }
    const style = new Map<string, { color: unknown; emissivity: unknown }>();
    const ambiguous: string[] = [];
    for (const r of curRois) {
      const k = String(r.name ?? '').trim();
      if (!k) continue;
      if (seen.get(k) === 1) style.set(k, { color: r.color, emissivity: r.emissivity });
      else if (!ambiguous.includes(k)) ambiguous.push(k);
    }

    const next = new Map(folderState);
    let n = 0;            // images whose shared settings were written
    let styledImgs = 0;   // images where at least one area was restyled
    let styledAreas = 0;  // areas restyled in total
    let noMatch = 0;      // images with no same-name area
    for (const path of selection) {
      if (path === activePath) continue;
      const prev = next.get(path);
      let rois = (prev?.rois as Array<Record<string, unknown>>) ?? [];
      if (areaMode === 'replace') {
        rois = curRois;
      } else if (areaMode === 'appearance') {
        let hit = 0;
        rois = rois.map((r) => {
          const s = style.get(String(r.name ?? '').trim());
          if (!s) return r;
          hit++;
          return { ...r, color: s.color, emissivity: s.emissivity };
        });
        if (hit) { styledImgs++; styledAreas += hit; } else noMatch++;
      }
      next.set(path, { ...shared, rois });
      n++;
    }
    folderState = next;

    const img = (k: number) => (k === 1 ? 'immagine' : 'immagini');
    if (areaMode === 'replace') {
      toast.success(`Impostazioni applicate a ${n} ${img(n)} (aree sostituite)`);
    } else if (areaMode === 'appearance') {
      let msg = `Impostazioni applicate a ${n} ${img(n)}. Aspetto allineato per ${styledAreas} `
        + `${styledAreas === 1 ? 'area' : 'aree'} in ${styledImgs} ${img(styledImgs)}`;
      if (noMatch) msg += `; ${noMatch} ${img(noMatch)} senza aree con lo stesso nome`;
      if (ambiguous.length) msg += `. Nomi non univoci sulla foto corrente, saltati: ${ambiguous.join(', ')}`;
      toast.success(msg);
    } else {
      toast.success(`Impostazioni applicate a ${n} ${img(n)}`);
    }
    regenThumbs(selection);
    // A bulk calibration change can shift the folder envelope — re-measure it.
    if (folderRange) { folderBounds = null; scanFolderRange(); }
  }

  async function ingestFolder(list: FileList | File[]) {
    const files = Array.from(list);
    for (const e of folder) URL.revokeObjectURL(e.thumb);

    const state = new Map<string, Record<string, unknown>>();
    const sidecars = new Map<string, Record<string, unknown>>();
    // Folder-session entries keyed by bare file name, so a session still applies
    // after the folder is renamed or the photos are re-exported (e.g. re-geotagged)
    // into a differently-named folder — the full relative path no longer matches
    // but the file name does.
    const sessionByBase = new Map<string, Record<string, unknown>>();
    let workspace: unknown = null;
    for (const f of files) {
      if (!/\.json$/i.test(f.name)) continue;
      try {
        const obj = JSON.parse(await f.text());
        if (obj && obj.warmish_folder_session != null && obj.files) {
          for (const [k, v] of Object.entries(obj.files)) {
            state.set(k, v as Record<string, unknown>);
            sessionByBase.set(fileBase(k), v as Record<string, unknown>);
          }
          if (obj.workspace) workspace = obj.workspace;
        } else {
          sidecars.set(stripExt(relPath(f)), obj);
        }
      } catch { /* ignore unreadable json */ }
    }

    const entries = files
      .filter((f) => /\.jpe?g$/i.test(f.name))
      .map((f) => ({ file: f, path: relPath(f), thumb: URL.createObjectURL(f) }))
      .sort((a, b) => a.path.localeCompare(b.path));
    for (const e of entries) {
      if (!state.has(e.path)) {
        const byBase = sessionByBase.get(fileBase(e.path));
        if (byBase) state.set(e.path, byBase);
      }
      const sc = sidecars.get(stripExt(e.path));
      if (sc && !state.has(e.path)) state.set(e.path, sc);
    }

    folder = entries;
    folderState = state;
    folderGps = new Map();
    folderTime = new Map();
    folderGpsScanned = false;
    folderBounds = null;
    folderRange = false;
    selection = new Set();
    activePath = null;
    page = 0;
    thumbParseCache.clear();
    thumbJobs = new Set();
    if (entries.length) {
      const wsActive = applyWorkspace(workspace);
      await openFromFolder(wsActive ?? entries[0].path);
      // The workspace block may have re-armed the common folder scale.
      if (folderRange) scanFolderRange();
      // Scan GPS up front so the "Mappa" badge shows the real count before the
      // map is ever opened — not just the single open image.
      scanFolderGps();
      // Tiles for images that came in with a saved session need to reflect it;
      // the rest keep their raw preview until the user opens or bulk-edits them.
      regenThumbs(entries.filter((e) => state.has(e.path)).map((e) => e.path));
    } else toast.error('La cartella non contiene immagini .jpg');
  }

  async function openFromFolder(path: string) {
    if (busy || path === activePath) return;
    const entry = folder.find((e) => e.path === path);
    if (!entry) return;
    if (activePath) {
      const s = snapshotSession();
      if (s) remember(activePath, s);
    }
    await load(entry.file);
    if (!file) { activePath = null; return; }
    activePath = path;
    const saved = folderState.get(path);
    if (saved) applySession(parseSession(saved), 'lavoro sulla cartella', false);
  }

  // Strip thumbnails start as the raw file previews, so on their own they never
  // reflect palette, range or parameter edits. Two mechanisms keep them honest,
  // so there is no manual "redraw" step:
  //   • the open image's tile is repainted by the $effect below, straight from
  //     the viewer's own composite — no re-parse, debounced so a slider drag
  //     repaints once, on release;
  //   • bulk edits (Applica impostazioni, a folder opened with saved sessions)
  //     call regenThumbs() for just the affected tiles, off the render path.
  // Both follow the folder-preview convention: the thermal layer is always
  // composited over the embedded photo (as the viewer's "Sovrapponi" does), and
  // the visible-photo *filter* is skipped — halftone/dither only read at 100 %,
  // not thumbnail size.
  const THUMB_W = 160;

  /** Folder paths whose tile is being regenerated — drives the per-tile spinner. */
  let thumbJobs = $state(new Set<string>());

  // Decoded thermal frames, kept so regenerating the same tile twice doesn't
  // re-parse the whole FLIR file. Cleared when the folder changes; capped so a
  // huge folder can't pin every frame in memory.
  const thumbParseCache = new Map<string, ThermalFile>();
  async function parseCached(e: FolderEntry): Promise<ThermalFile> {
    const hit = thumbParseCache.get(e.path);
    if (hit) return hit;
    const parsed = parseThermalImage(new Uint8Array(await e.file.arrayBuffer()));
    thumbParseCache.set(e.path, parsed);
    if (thumbParseCache.size > 240) {
      thumbParseCache.delete(thumbParseCache.keys().next().value as string);
    }
    return parsed;
  }

  /** Render one folder entry's preview through the full thermal pipeline, using
   *  its saved session when it has one. */
  async function renderEntryThumb(e: FolderEntry): Promise<string | null> {
    try {
      const parsed = await parseCached(e);
      const saved = folderState.get(e.path);
      const patch = saved ? parseSession(saved) : null;
      const p = parametersFromMetadata(parsed.metadata);
      if (patch?.parameters) Object.assign(p, patch.parameters);
      const temps = computeTemperatures(parsed.raw, p);
      const r = folderScaleActive
        ? folderBounds!
        : patch && patch.autoRange === false
          ? { min: patch.manualMin ?? 0, max: patch.manualMax ?? 100 }
          : (patch?.stretchPct ? percentileRange(temps, patch.stretchPct) : temperatureRange(temps));
      const px = colorize(temps, {
        palette: patch?.palette ?? DEFAULT_PALETTE,
        inverted: patch?.inverted ?? false,
        min: r.min, max: r.max,
      });
      const thermal = imageDataToCanvas(px, parsed.width, parsed.height);

      let rendered: CanvasImageSource & { width: number; height: number } =
        thermal as CanvasImageSource & { width: number; height: number };
      if (parsed.visible) {
        const bmp = await createImageBitmap(
          new Blob([parsed.visible as BlobPart], { type: 'image/jpeg' }),
        );
        rendered = composite({
          thermal,
          width: parsed.width,
          height: parsed.height,
          visible: bmp as CanvasImageSource & { width: number; height: number },
          blend: patch?.blend ?? blend,
          opacity: patch?.opacity ?? opacity,
          alignment: patch?.alignment ?? alignmentFromMetadata(parsed.metadata),
        }).canvas as CanvasImageSource & { width: number; height: number };
        bmp.close();
      }
      return downscale(rendered, THUMB_W).toDataURL('image/jpeg', 0.72);
    } catch {
      return null; // keep the old preview if this one won't decode
    }
  }

  /** Swap one folder entry's thumb in place, revoking a blob URL it replaces. */
  function setThumb(path: string, url: string) {
    untrack(() => {
      const i = folder.findIndex((x) => x.path === path);
      if (i < 0) return;
      const prev = folder[i].thumb;
      const next = folder.slice();
      next[i] = { ...next[i], thumb: url };
      folder = next;
      if (prev.startsWith('blob:')) URL.revokeObjectURL(prev);
    });
  }

  /** Repaint the given tiles from their saved sessions, one at a time so the UI
   *  stays responsive. The open image is left to the $effect below. */
  async function regenThumbs(paths: Iterable<string>) {
    const active = untrack(() => activePath);
    const queue = [...new Set(paths)].filter((p) => p !== active);
    if (!queue.length) return;
    thumbJobs = new Set([...thumbJobs, ...queue]);
    for (const path of queue) {
      const e = untrack(() => folder.find((x) => x.path === path));
      if (e) {
        const url = await renderEntryThumb(e);
        if (url) setThumb(path, url);
      }
      thumbJobs = new Set([...thumbJobs].filter((p) => p !== path));
    }
  }

  /** A large processed frame for the map tour — the same pixels an export of
   *  this image would produce (palette, range, overlay, filter, areas). Rendered
   *  on demand as the tour nears a stop; the caller owns the returned blob URL. */
  async function renderTourImage(path: string): Promise<string | null> {
    try {
      let bytes: Uint8Array;
      let settings: RenderSettings;
      if (folder.length) {
        const i = folder.findIndex((e) => e.path === path);
        if (i < 0) return null;
        bytes = new Uint8Array(await folder[i].file.arrayBuffer());
        if (path === activePath) {
          settings = currentSettings();
        } else {
          const ov = folderOverrides()[i];
          settings = ov ? { ...renderSettings(), ...ov } : renderSettings();
        }
      } else {
        if (!currentFile) return null;
        bytes = new Uint8Array(await currentFile.arrayBuffer());
        settings = currentSettings();
      }
      const blob = await renderHeroImage(bytes, settings);
      return URL.createObjectURL(blob);
    } catch {
      return null;
    }
  }

  // The open image's tile, kept in sync with the viewer. Reads the same render
  // inputs, then debounces: a slider drag runs this once, ~300 ms after release.
  let activeThumbTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const canvas = thermalCanvas;          // palette, inverted, range, params, file
    void visibleBitmap; void blend; void opacity;
    void JSON.stringify(alignment);         // dx / dy / scale
    const path = activePath;
    if (!path || !canvas) return;
    clearTimeout(activeThumbTimer);
    activeThumbTimer = setTimeout(() => {
      if (untrack(() => activePath) !== path) return;
      const url = thumbDataUrl(THUMB_W);
      if (url) setThumb(path, url);
    }, 300);
  });

  function navFolder(delta: number) {
    if (busy || !folder.length) return;
    const i = folder.findIndex((e) => e.path === activePath);
    const j = Math.min(folder.length - 1, Math.max(0, (i < 0 ? 0 : i) + delta));
    page = Math.floor(j / PAGE);
    openFromFolder(folder[j].path);
  }

  $effect(() => {
    try { localStorage.setItem('warmish.filmstrip', filmstripOpen ? '1' : '0'); } catch { /* private mode */ }
  });

  function onWindowKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape' && bulkOpen) { bulkOpen = false; return; }
    const tag = (ev.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if ((ev.key === 'm' || ev.key === 'M') && file) {
      setViewMode(viewMode === 'map' ? 'thermal' : 'map');
      return;
    }
    // Area tools, when the thermal canvas is on screen.
    if (file && viewMode === 'thermal' && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
      const k = ev.key.toLowerCase();
      const pick: Record<string, Tool> = { v: 'pan', r: 'rect', s: 'spot', p: 'polygon' };
      if (pick[k]) { tool = pick[k]; return; }
    }
    if (!folder.length) return;
    if (ev.key === 'ArrowRight') navFolder(1);
    else if (ev.key === 'ArrowLeft') navFolder(-1);
    else if (ev.key === 'f' || ev.key === 'F') filmstripOpen = !filmstripOpen;
  }

  /** Drop `undefined` keys so a partial sidecar can't blank a base setting. */
  const defined = <T extends object>(o: T): Partial<T> =>
    Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as Partial<T>;

  /** Per-image render overrides for the folder batch, parallel to `folder`. */
  function folderOverrides(): (Partial<RenderSettings> | null)[] {
    // Under the common folder scale the range is pinned for every image by the
    // base settings, so a per-image saved range must not override it.
    const pinRange = folderScaleActive;
    return folder.map((e) => {
      const saved = folderState.get(e.path);
      if (!saved) return null;
      const p = parseSession(saved);
      return defined({
        palette: p.palette, inverted: p.inverted,
        autoRange: pinRange ? undefined : p.autoRange,
        stretchPct: pinRange ? undefined : p.stretchPct,
        manualMin: pinRange ? undefined : p.manualMin,
        manualMax: pinRange ? undefined : p.manualMax,
        blend: p.blend, opacity: p.opacity,
        alignment: p.alignment, visibleFilter: p.visibleFilter, labels: p.labels,
        rois: p.rois ? p.rois.map((r) => $state.snapshot(r) as Roi) : undefined,
        parameters: p.parameters ? (p.parameters as UserParameters) : undefined,
      });
    });
  }

  // --- Export ----------------------------------------------------------------
  // Both zip paths — the current image and the whole folder — report through
  // these; the work itself runs in the one worker in `dispatchExport`.
  let includeOriginals = $state(true);
  let batchProgress = $state<{ done: number; total: number; name: string } | null>(null);

  /**
   * The base settings for a folder export: everything the folder path pins the
   * same for every image (palette range mode, blend, labels…). Per-image edits
   * ride on top as `folderOverrides()`; images never touched fall back to this
   * with their own embedded calibration (`parameters: null`) and their own areas
   * (cleared here, restored per image by the overrides).
   */
  function renderSettings(): RenderSettings {
    return {
      palette, inverted, ...rangeSettings(), showVisible,
      blend, opacity,
      alignment: { ...alignment },
      visibleFilter: { ...visibleFilter },
      labels: { ...labels },
      rois: [],
      parameters: null,
    };
  }

  /**
   * Every export path — one image, a batch, or a whole folder — goes through the
   * worker, so the zip it produces has exactly one structure. The desktop writes
   * into a chosen folder; a page cannot, so a single archive is the closest
   * faithful equivalent.
   */
  function dispatchExport(
    files: File[],
    settings: RenderSettings,
    perFile: (Partial<RenderSettings> | null)[] | undefined,
    withOriginals: boolean,
  ) {
    if (!files.length || batchProgress) return;
    batchProgress = { done: 0, total: files.length, name: '' };
    const exportDate = new Date().toISOString().slice(0, 10);
    const zipName = `warmish_export_${exportDate}.zip`;
    const one = files.length === 1;
    const prog = progressToast(one ? 'Elaborazione dell’immagine…' : `Elaborazione di ${files.length} immagini…`);

    const worker = new Worker(new URL('./lib/batch.worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (ev: MessageEvent<BatchMessage>) => {
      const m = ev.data;
      if (m.type === 'progress') {
        batchProgress = { done: m.done, total: m.total, name: m.name };
        prog.update(m.done, m.total, one ? 'Elaborazione…' : `${m.done}/${m.total} · ${m.name}`);
      } else if (m.type === 'done') {
        download(new Blob([m.zip], { type: 'application/zip' }), zipName);
        if (m.failures.length) {
          prog.finish('error', `${m.processed} immagini elaborate, ${m.failures.length} non riuscite (vedi errori.txt nello ZIP)`);
        } else {
          prog.finish('success', one ? 'Immagine esportata' : `${m.processed} immagini esportate`);
        }
        batchProgress = null;
        worker.terminate();
      } else {
        prog.finish('error', `Errore: ${m.message}`);
        batchProgress = null;
        worker.terminate();
      }
    };
    worker.onerror = (e) => {
      prog.finish('error', `Errore nel worker: ${e.message}`);
      batchProgress = null;
      worker.terminate();
    };
    worker.postMessage({
      files, settings, perFile,
      includeOriginals: withOriginals,
      exportDate,
      warmishVersion: APP_VERSION,
    } satisfies BatchRequest);
  }

  async function exportFolderZip() {
    // Every image, each carrying its own edited state (or its sidecar); images
    // never touched keep their own calibration and auto-range.
    if (activePath) {
      const s = snapshotSession();
      if (s) remember(activePath, s);
    }
    // The common folder scale must be resolved to fixed bounds before dispatch.
    if (folderRange && !folderBounds) await scanFolderRange();
    dispatchExport(
      folder.map((e) => e.file),
      renderSettings(),
      folderOverrides(),
      includeOriginals,
    );
  }

  const fmt = (v: number | undefined) => (v !== undefined && Number.isFinite(v) ? v.toFixed(2) : '—');

  /** Any CSS colour (a `roiColor()` `hsl(...)` or a stored `#rrggbb`) → `#rrggbb`,
   *  the only form the native `<input type="color">` accepts. */
  const hexCtx = document.createElement('canvas').getContext('2d')!;
  function colorToHex(c: string): string {
    hexCtx.fillStyle = '#000';
    hexCtx.fillStyle = c;
    const v = hexCtx.fillStyle;
    if (v[0] === '#') return v;
    const m = /(\d+),\s*(\d+),\s*(\d+)/.exec(v);
    return m ? '#' + ((+m[1] << 16) | (+m[2] << 8) | +m[3]).toString(16).padStart(6, '0') : '#ff0000';
  }

  /**
   * Number inputs show a rounded value but keep the file's full float32 precision
   * underneath, so simply opening an image never perturbs the computed temperatures.
   */
  const shown = (v: number, digits = 1) => Number(v.toFixed(digits));
  const edit = (key: keyof ThermalParameters) => (ev: Event) => {
    const v = Number((ev.currentTarget as HTMLInputElement).value);
    if (params && Number.isFinite(v)) params[key] = v;
  };
</script>

<svelte:window
  onkeydown={onWindowKey}
  onclick={(e) => {
    if (openMenu && !(e.target as HTMLElement).closest?.('.menu')) openMenu = false;
  }}
/>

<div class="app" class:touring={tourMode} ondragover={(e) => e.preventDefault()} ondrop={onDrop} role="application">
  <header class="topbar">
    <h1 class="brand">Warmish <span>Web</span></h1>

    <details class="menu" bind:open={openMenu}>
      <summary>Apri</summary>
      <div class="menu-pop">
        <button onclick={() => { openMenu = false; document.getElementById('pick')?.click(); }}>
          Immagine o immagini…
        </button>
        <button onclick={() => { openMenu = false; document.getElementById('folderpick')?.click(); }}>
          Cartella di immagini…
        </button>
        <hr />
        <button disabled={!file} onclick={() => { openMenu = false; showExif = true; }}>
          Dati EXIF…
        </button>
        <a href="geotag/index.html" target="_blank" rel="noopener" onclick={() => (openMenu = false)}>
          Geotag: correggi il GPS…
        </a>
        <p class="menu-hint">Puoi anche trascinare i file in questa finestra.</p>
      </div>
    </details>

    {#if fileName}<span class="cur" title={fileName}>{fileName}</span>{/if}
    {#if folder.length}<span class="cur muted">cartella · {folder.length} img</span>{/if}

    <div class="grow"></div>

    {#if file}
      <div class="viewswitch" role="group" aria-label="Modalità di visualizzazione">
        <button class:on={viewMode === 'thermal'} aria-pressed={viewMode === 'thermal'} onclick={() => setViewMode('thermal')}>Termica</button>
        <button
          class:on={viewMode === 'map'}
          aria-pressed={viewMode === 'map'}
          onclick={() => setViewMode('map')}
          title="Posiziona sulla mappa le foto con coordinate GPS (M)"
        >
          Mappa{#if mapCount}<span class="badge">{mapCount}</span>{/if}
        </button>
      </div>
      <button onclick={() => (activeTab = 'esporta')}>Esporta</button>
    {/if}
    <button
      class="icon"
      onclick={cycleTheme}
      aria-label={`Tema: ${THEME_LABEL[theme]}. Cambia.`}
      title={`Tema: ${THEME_LABEL[theme]}`}
    >{THEME_GLYPH[theme]}</button>
    <button class="icon" onclick={() => (showHelp = true)} aria-label="Aiuto e scorciatoie" title="Aiuto e scorciatoie">?</button>
  </header>

  <div class="layout">
  <aside>
    <!-- Driven by the "Apri" menu in the top bar and by drag-and-drop. -->
    <input id="pick" class="sr-only" type="file" multiple accept="image/jpeg,.jpg,.jpeg,.json" onchange={onPick} />
    <input id="folderpick" class="sr-only" type="file" webkitdirectory multiple
      onchange={(e) => { const l = (e.currentTarget as HTMLInputElement).files; if (l?.length) ingestFolder(l); }} />

    {#if file && params}
      <div class="tabs" role="tablist" aria-label="Pannelli">
        {#each TAB_LABELS as [id, label] (id)}
          <button
            role="tab"
            id={`tab-${id}`}
            aria-controls="tabpanel"
            aria-selected={activeTab === id}
            tabindex={activeTab === id ? 0 : -1}
            class:active={activeTab === id}
            onclick={() => (activeTab = id)}
            onkeydown={onTabKey}
          >{label}</button>
        {/each}
      </div>

      <div class="panel" role="tabpanel" id="tabpanel" aria-labelledby={`tab-${activeTab}`} tabindex="-1">
      {#if activeTab === 'immagine'}
      <section>
        <h2>Palette</h2>
        <select bind:value={palette}>
          {#each PALETTE_NAMES as name}<option value={name}>{name}</option>{/each}
        </select>
        <label class="check"><input type="checkbox" bind:checked={inverted} /> Invertita</label>
        <label class="check"><input type="checkbox" bind:checked={showLegend} /> Scala colori</label>
      </section>

      <section>
        <h2>Intervallo</h2>
        <label class="check"><input type="checkbox" bind:checked={autoRange} /> Automatico</label>
        {#if autoRange}
          <label for="stretch">Contrasto</label>
          <select
            id="stretch"
            value={folderRange ? 'folder' : String(stretchPct)}
            onchange={(e) => {
              const v = (e.currentTarget as HTMLSelectElement).value;
              if (v === 'folder') enableFolderRange();
              else { folderRange = false; stretchPct = Number(v); }
            }}
          >
            <option value="0">Min/Max reali</option>
            <option value="90">Stretch 90%</option>
            <option value="98">Stretch 98%</option>
            {#if !folderRange && stretchPct !== 0 && stretchPct !== 90 && stretchPct !== 98}
              <option value={String(stretchPct)}>Stretch {+stretchPct.toFixed(1)}%</option>
            {/if}
            {#if folder.length}
              <option value="folder">Comune alla cartella</option>
            {/if}
          </select>
          {#if folderRange}
            <p class="hint">
              {#if folderRangeScanning}Scansione della cartella…
              {:else if folderBounds}Scala fissa {folderBounds.min.toFixed(1)}–{folderBounds.max.toFixed(1)} °C su tutte le {folder.length} immagini.
              {:else}Scala comune non disponibile.{/if}
            </p>
          {/if}
        {:else}
          <div class="row">
            <div><label for="mn">Min °C</label><input id="mn" type="number" step="0.1" bind:value={manualMin} /></div>
            <div><label for="mx">Max °C</label><input id="mx" type="number" step="0.1" bind:value={manualMax} /></div>
          </div>
        {/if}
      </section>

      {#if file.visible}
        <section>
          <h2>Immagine visibile</h2>
          <label class="check"><input type="checkbox" bind:checked={showVisible} /> Sovrapponi la foto reale</label>
          {#if showVisible}
            <label for="bl">Fusione</label>
            <select id="bl" bind:value={blend}>
              {#each BLEND_NAMES as name}<option value={name}>{name}</option>{/each}
            </select>
            <label for="op">Opacità termica: {Math.round(opacity * 100)}%</label>
            <input id="op" type="range" min="0" max="1" step="0.01" bind:value={opacity} />
          {/if}
        </section>
      {/if}

      {#if stats}
        <section>
          <h2>Statistiche</h2>
          <dl>
            <dt>Min</dt><dd>{fmt(stats.min)} °C</dd>
            <dt>Max</dt><dd>{fmt(stats.max)} °C</dd>
            <dt>Media</dt><dd>{fmt(stats.mean)} °C</dd>
            <dt>Sensore</dt><dd>{file.width}×{file.height}</dd>
          </dl>
        </section>
      {/if}

      <details class="advanced" bind:open={advOpen}>
        <summary>Avanzate</summary>

        <div class="adv">
          <h3>Calibrazione</h3>
          <label for="em">Emissività: {params.Emissivity.toFixed(2)}</label>
          <input id="em" type="range" min="0.1" max="1" step="0.01" bind:value={params.Emissivity} />
          <label for="rt">Temp. riflessa apparente (°C)</label>
          <input id="rt" type="number" step="0.5" value={shown(params.ReflectedApparentTemperature)} onchange={edit('ReflectedApparentTemperature')} />
          <label for="at">Temp. atmosferica (°C)</label>
          <input id="at" type="number" step="0.5" value={shown(params.AtmosphericTemperature)} onchange={edit('AtmosphericTemperature')} />
          <label for="rh">Umidità relativa (%)</label>
          <input id="rh" type="number" step="1" value={shown(params.RelativeHumidity, 0)} onchange={edit('RelativeHumidity')} />
        </div>

        {#if file.visible}
          <div class="adv">
            <h3>Foto reale</h3>
            <label for="vf">Filtro</label>
            <select
              id="vf"
              value={visibleFilter.name}
              onchange={(e) => {
                const name = (e.currentTarget as HTMLSelectElement).value as FilterName;
                visibleFilter = { name, strength: filterPreset(name) };
              }}
            >
              {#each FILTERS as f}<option value={f.name}>{f.label}</option>{/each}
            </select>
            {#if visibleFilter.name !== 'none'}
              <label for="vfs">Intensità: {visibleFilter.strength}%</label>
              <input id="vfs" type="range" min="0" max="100" step="1" bind:value={visibleFilter.strength} />
            {/if}
          </div>

          <div class="adv">
            <h3>Allineamento termico</h3>
            <label for="al">Scala: {alignment.scale.toFixed(2)}×</label>
            <input id="al" type="range" min="0.1" max="5" step="0.01" bind:value={alignment.scale} />
            <div class="row">
              <div><label for="ox">Offset X</label><input id="ox" type="number" step="1" bind:value={alignment.offsetX} /></div>
              <div><label for="oy">Offset Y</label><input id="oy" type="number" step="1" bind:value={alignment.offsetY} /></div>
            </div>
            <button class="wide" onclick={() => (alignment = file ? alignmentFromMetadata(file.metadata) : { ...DEFAULT_ALIGNMENT })}>Reimposta allineamento</button>
          </div>
        {/if}
      </details>
      {/if}

      {#if activeTab === 'aree'}
      <section>
        <h2>Aree di interesse</h2>
        <p class="hint">
          Gli strumenti di disegno sono sulla barra a sinistra dell’immagine
          (o con i tasti V, R, S, P).
        </p>

        {#if rois.length}
          <ul class="rois">
            {#each rois as roi (roi.id)}
              {@const s = roiStats.get(roi.id)}
              <li class:sel={roi.id === selectedId}>
                <label class="swatch">
                  <span class="dot" style="background:{roi.color}"></span>
                  <input
                    type="color"
                    aria-label={`Colore di ${roi.name}`}
                    value={colorToHex(roi.color)}
                    oninput={(e) => (roi.color = e.currentTarget.value)}
                  />
                </label>
                <button class="pick" aria-pressed={roi.id === selectedId} onclick={() => (selectedId = roi.id)}>
                  <span class="nm">{roi.name}</span>
                  <span class="tm">{fmt(s?.mean)} °C</span>
                </button>
                <button class="del" onclick={() => deleteRoi(roi.id)} aria-label={`Elimina ${roi.name}`} title="Elimina">×</button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="hint">Nessuna area. Scegli uno strumento e disegna sull’immagine.</p>
        {/if}

        {#if selected}
          {@const s = roiStats.get(selected.id)}
          <div class="detail">
            <label for="rn">Nome</label>
            <input id="rn" type="text" bind:value={selected.name} />
            <label for="re">Emissività area: {selected.emissivity.toFixed(2)}</label>
            <input id="re" type="range" min="0.1" max="1" step="0.01" bind:value={selected.emissivity} />
            <dl>
              <dt>Min</dt><dd>{fmt(s?.min)} °C</dd>
              <dt>Max</dt><dd>{fmt(s?.max)} °C</dd>
              <dt>Media</dt><dd>{fmt(s?.mean)} °C</dd>
              <dt>Mediana</dt><dd>{fmt(s?.median)} °C</dd>
              <dt>Dev. std</dt><dd>{fmt(s?.std)} °C</dd>
              <dt>Pixel</dt><dd>{s?.pixels ?? 0}</dd>
            </dl>
          </div>
        {/if}

        <details>
          <summary>Etichette</summary>
          <label class="check"><input type="checkbox" bind:checked={labels.name} /> Nome</label>
          <label class="check"><input type="checkbox" bind:checked={labels.emissivity} /> Emissività</label>
          <label class="check"><input type="checkbox" bind:checked={labels.min} /> Min</label>
          <label class="check"><input type="checkbox" bind:checked={labels.max} /> Max</label>
          <label class="check"><input type="checkbox" bind:checked={labels.avg} /> Media</label>
          <label class="check"><input type="checkbox" bind:checked={labels.median} /> Mediana</label>
          <label for="label-scale">Dimensione etichette: {Math.round(labels.scale * 100)}%</label>
          <input
            id="label-scale"
            type="range"
            min="0.6"
            max="2.5"
            step="0.05"
            bind:value={labels.scale}
          />
        </details>
      </section>
      {/if}

      {#if activeTab === 'esporta'}
      <section class="actions">
        <h2>Immagine corrente</h2>
        <button class="wide" onclick={exportZip} disabled={!currentFile || !!batchProgress}>
          {batchProgress ? 'Elaborazione…' : 'Esporta (.zip)'}
        </button>
        <button onclick={exportSession}>Salva sessione (.json)</button>
        <label class="check">
          <input type="checkbox" bind:checked={includeOriginals} />
          Includi gli originali nello ZIP
        </label>
        <p class="hint">
          Termica pulita e annotata, foto reale, <code>aree.csv</code> e sessione.
          <button class="linkish" onclick={() => (showHelp = true)}>Dettagli</button>
        </p>
      </section>

      {#if folder.length}
        <section class="actions">
          <h2>Cartella aperta ({folder.length} immagini)</h2>
          <button class="wide" onclick={exportFolderZip} disabled={!!batchProgress}>
            {batchProgress ? 'Elaborazione…' : 'Esporta cartella (.zip)'}
          </button>
          <button onclick={exportFolderSession} disabled={!!batchProgress}>
            Salva sessione cartella (.json)
          </button>
          <p class="hint">
            Ogni immagine con la propria calibrazione e le proprie modifiche.
            <button class="linkish" onclick={() => (showHelp = true)}>Dettagli</button>
          </p>
        </section>
      {/if}
      {/if}
      </div>
    {:else}
      <p class="hint aside-empty">
        Apri un’immagine per accedere a palette, parametri, aree ed esportazione.
      </p>
    {/if}
  </aside>

  <main>
    {#if busy}
      <div class="empty">Elaborazione…</div>
    {:else if file}
      <div class="pane" class:hidden={viewMode !== 'thermal'}>
        <Viewer
          bind:this={viewer}
          image={view}
          {rois}
          stats={roiStats}
          {labels}
          {tool}
          {selectedId}
          onprobe={onProbe}
          onzoom={(p) => (zoomPct = p)}
          onselect={(id) => (selectedId = id)}
          onroicreate={addRoi}
          ondelete={deleteRoi}
          ontoolreset={() => (tool = 'pan')}
        />
      </div>
      {#if viewMode === 'thermal'}
        <ToolRail {tool} onpick={(t) => (tool = t)} />
        {#if showLegend && temperatures}
          <RangeScale
            lut={getLut(palette)}
            {inverted}
            dataMin={scaleDomain.min}
            dataMax={scaleDomain.max}
            min={range.min}
            max={range.max}
            {histogram}
            auto={autoRange}
            {stretchPct}
            folderMode={folderScaleActive}
            folderAvailable={folder.length > 0}
            scanning={folderRange && folderRangeScanning}
            onchange={(mn, mx) => { autoRange = false; folderRange = false; manualMin = mn; manualMax = mx; }}
            onauto={resetRange}
            oncycle={cycleRange}
            onstretch={setStretch}
            onfolder={enableFolderRange}
          />
        {/if}
      {/if}
      {#if viewMode === 'map'}
        <div class="pane">
          <MapView
            points={mapPoints}
            onopen={openFromMap}
            tourImage={renderTourImage}
            ontour={(active) => (tourMode = active)}
          />
        </div>
      {/if}
    {:else}
      <div class="empty big">
        <h2>Editor termico FLIR, tutto nel browser</h2>
        <p>
          Apri una foto radiometrica FLIR per rimappare la palette, correggere i
          parametri di calibrazione, misurare aree e temperature ed esportare le
          immagini pronte. Più foto o una cartella si modificano in blocco e si
          esportano in un solo ZIP.
        </p>
        <div class="empty-actions">
          <button class="primary" onclick={() => document.getElementById('pick')?.click()}>Apri immagini…</button>
          <button onclick={() => document.getElementById('folderpick')?.click()}>Apri una cartella…</button>
        </div>
        <small>
          Trascina qui i file. Tutto viene elaborato sul tuo computer: nessun
          file viene caricato online.
        </small>
      </div>
    {/if}
  </main>
  </div>

  {#if folder.length}
    <nav class="strip" class:collapsed={!filmstripOpen} aria-label="Immagini della cartella">
      <div class="strip-bar">
        <button
          class="toggle"
          onclick={() => (filmstripOpen = !filmstripOpen)}
          aria-expanded={filmstripOpen}
          title={filmstripOpen ? 'Nascondi la striscia (F)' : 'Mostra la striscia (F)'}
        >{filmstripOpen ? '▾' : '▸'}</button>
        <span>{folder.length} immagini{#if selectedCount} · {selectedCount} selezionate{/if}</span>
        {#if thumbJobs.size}
          <span class="strip-jobs">· aggiorno {thumbJobs.size} {thumbJobs.size === 1 ? 'anteprima' : 'anteprime'}…</span>
        {/if}
        <div class="grow"></div>
        {#if pageCount > 1}
          <div class="pager">
            <button disabled={page === 0} onclick={() => (page -= 1)} aria-label="Pagina precedente">‹</button>
            <span>{page + 1}/{pageCount}</span>
            <button disabled={page >= pageCount - 1} onclick={() => (page += 1)} aria-label="Pagina successiva">›</button>
          </div>
        {/if}
        <button class="bulk-open" disabled={!activePath} onclick={() => (bulkOpen = true)}>
          Modifica in blocco{#if selectedCount}&nbsp;({selectedCount}){/if}…
        </button>
      </div>
      {#if filmstripOpen}
        <div class="strip-scroll">
          {#each pageEntries as e (e.path)}
            <div class="thumb-wrap" class:sel={selection.has(e.path)} class:busy={thumbJobs.has(e.path)}>
              <button
                class="thumb"
                class:on={e.path === activePath}
                onclick={() => openFromFolder(e.path)}
                title={e.path}
              >
                <img src={e.thumb} alt={e.path} loading="lazy" />
                {#if folderState.has(e.path)}<span class="edited" title="Ha modifiche salvate"></span>{/if}
                {#if thumbJobs.has(e.path)}<span class="thumb-spin" aria-hidden="true"></span>{/if}
              </button>
              <input
                class="pick"
                type="checkbox"
                checked={selection.has(e.path)}
                onchange={() => toggleSelect(e.path)}
                aria-label={`Seleziona ${e.path.split('/').pop()}`}
                title="Seleziona per la modifica in blocco"
              />
            </div>
          {/each}
        </div>
      {/if}
    </nav>
  {/if}

  {#if file}
    <footer class="statusbar">
      <span class="z">{zoomPct}%</span>
      <button class="linkish" onclick={() => viewer?.fit()}>Adatta</button>
      <span class="sep">·</span>
      <span>{file.width}×{file.height}</span>
      {#if probe && viewMode === 'thermal'}
        <span class="sep">·</span>
        <span class="probe-read">x{probe.x} y{probe.y} → <strong>{fmt(probe.t)} °C</strong></span>
      {/if}
      <div class="grow"></div>
      <span>{palette}{#if inverted} · invertita{/if}</span>
      <span class="sep">·</span>
      <span>
        {#if !autoRange}{`${fmt(range.min)}–${fmt(range.max)} °C`}
        {:else if folderRange && folderRangeScanning}scansione cartella…
        {:else if folderScaleActive}{`scala cartella · ${fmt(range.min)}–${fmt(range.max)} °C`}
        {:else if stretchPct > 0}{`stretch ${+stretchPct.toFixed(1)}% · ${fmt(range.min)}–${fmt(range.max)} °C`}
        {:else}intervallo auto{/if}
      </span>
      {#if gps}<span class="sep">·</span><span title="Coordinate GPS presenti nella foto">GPS</span>{/if}
    </footer>
  {/if}
</div>

{#if showExif && file}
  <ExifModal {exif} metadata={file.metadata} {fileName} onclose={() => (showExif = false)} />
{/if}
{#if showHelp}
  <HelpModal onclose={() => (showHelp = false)} />
{/if}

<Toasts />

{#if bulkOpen}
  <button type="button" class="sheet-scrim" aria-label="Chiudi" onclick={() => (bulkOpen = false)}></button>
  <div class="sheet" role="dialog" aria-modal="true" aria-label="Modifica in blocco" tabindex="-1" use:dialog>
    <header>
      <h2>Modifica in blocco</h2>
      <button class="x" onclick={() => (bulkOpen = false)} aria-label="Chiudi">×</button>
    </header>
    <div class="sheet-body">
      <div class="sel-row">
        <span>{selectedCount} di {folder.length} selezionate</span>
        <div class="grow"></div>
        <button onclick={selectAll}>Tutte</button>
        <button onclick={selectNone}>Nessuna</button>
        <button onclick={invertSelection}>Inverti</button>
      </div>

      <p class="hint">
        Copia dall’immagine corrente
        {#if activePath}(<strong>{activePath.split('/').pop()}</strong>){/if}
        alle selezionate: palette, intervallo, parametri termici, allineamento ed
        etichette.
      </p>

      <fieldset class="area-modes" disabled={!rois.length}>
        <legend>Aree</legend>
        <label>
          <input type="radio" name="bulkArea" value="none" bind:group={areaMode} />
          <span><strong>Lascia invariate</strong><small>Le aree di ogni immagine restano come sono.</small></span>
        </label>
        <label>
          <input type="radio" name="bulkArea" value="appearance" bind:group={areaMode} />
          <span><strong>Uniforma l’aspetto</strong><small>Colore ed emissività delle aree con lo stesso nome vengono allineati a quelli correnti. Posizione e forma restano di ogni foto; le temperature possono cambiare se cambia l’emissività.</small></span>
        </label>
        <label>
          <input type="radio" name="bulkArea" value="replace" bind:group={areaMode} />
          <span><strong>Sostituisci</strong><small>Le aree correnti, posizioni incluse, rimpiazzano quelle di ogni immagine.</small></span>
        </label>
      </fieldset>
      {#if !rois.length}
        <p class="hint">L’immagine corrente non ha aree: le opzioni sopra sono disattivate.</p>
      {/if}
    </div>
    <footer>
      <button onclick={() => (bulkOpen = false)}>Annulla</button>
      <button
        class="primary"
        disabled={!activePath || selectedCount === 0}
        onclick={() => { applyToSelected(); bulkOpen = false; }}
      >
        Applica a {selectedCount} {selectedCount === 1 ? 'immagine' : 'immagini'}
      </button>
    </footer>
  </div>
{/if}

<style>
  /* One implicit `auto` row grew to the sidebar's content height, pushing the
     whole layout past the viewport — so `main` (and the canvas host inside it)
     ended up taller than the screen and `fit()` scaled to that phantom height.
     Pin the row to the viewport and let each column scroll on its own. */
  .app { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .layout {
    flex: 1; min-height: 0;
    display: grid; grid-template-columns: 300px 1fr;
    grid-template-rows: minmax(0, 1fr); overflow: hidden;
  }

  /* Map tour: strip the shell to just the map. MapView's own panel (with its
     ✕ / Esc) is the only way out, and leaving restores everything. */
  .app.touring > .topbar,
  .app.touring > .strip,
  .app.touring > .statusbar,
  .app.touring .layout > aside {
    display: none;
  }
  .app.touring .layout { grid-template-columns: 1fr; }

  /* --- Top bar ------------------------------------------------------------ */
  .topbar {
    flex: none; display: flex; align-items: center; gap: 10px;
    height: 48px; padding: 0 12px;
    background: var(--panel); border-bottom: 1px solid var(--line);
  }
  .topbar .grow { flex: 1; }
  .brand { margin: 0; font-size: 15px; font-weight: 600; letter-spacing: -0.2px; white-space: nowrap; }
  .brand span { color: var(--accent); font-weight: 400; }
  .topbar .cur {
    font-size: 12px; color: var(--text); max-width: 240px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .topbar .cur.muted { color: var(--muted); }
  .topbar > button {
    flex: none; padding: 6px 12px; font-size: 13px;
  }
  .topbar .icon {
    width: 30px; height: 30px; padding: 0; border-radius: 999px;
    display: grid; place-items: center; font-size: 14px;
  }

  .menu { position: relative; flex: none; }
  .menu > summary {
    list-style: none; cursor: pointer; user-select: none;
    background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
    padding: 6px 12px; font-size: 13px;
  }
  .menu > summary::-webkit-details-marker { display: none; }
  .menu > summary::after { content: ' ▾'; color: var(--muted); }
  .menu > summary:hover { border-color: var(--accent); }
  .menu-pop {
    position: absolute; top: calc(100% + 4px); left: 0; z-index: 30;
    min-width: 230px; padding: 4px;
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    display: grid; gap: 2px;
  }
  .menu-pop button, .menu-pop a {
    display: block; width: 100%; text-align: left;
    padding: 8px 10px; font-size: 13px; text-decoration: none;
    color: var(--text); background: transparent; border: 0; border-radius: 5px; cursor: pointer;
  }
  .menu-pop button:hover, .menu-pop a:hover { background: var(--bg); border-color: transparent; }
  .menu-pop button:disabled { color: var(--muted); cursor: default; background: transparent; }
  .menu-pop hr { margin: 4px 2px; border: 0; border-top: 1px solid var(--line); }
  .menu-hint { margin: 4px 6px 2px; font-size: 12px; color: var(--muted); line-height: 1.4; }

  /* --- Status bar ------------------------------------------------------- */
  .statusbar {
    flex: none; display: flex; align-items: center; gap: 8px;
    height: 28px; padding: 0 12px;
    background: var(--panel); border-top: 1px solid var(--line);
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums;
  }
  .statusbar .grow { flex: 1; }
  .statusbar .sep { opacity: 0.45; }
  .statusbar .z { color: var(--text); }
  .statusbar strong { color: var(--text); font-weight: 600; }
  .statusbar .linkish { font-size: 12px; }

  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }
  .aside-empty { margin-top: 0; }

  /* --- Filmstrip (navigation only) ------------------------------------- */
  .strip {
    flex: none; min-width: 0;
    background: var(--panel); border-top: 1px solid var(--line);
    display: flex; flex-direction: column;
  }
  .strip-bar {
    display: flex; align-items: center; gap: 8px; padding: 5px 10px;
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums;
  }
  .strip-bar .grow { flex: 1; }
  .strip-bar .toggle {
    flex: none; background: transparent; border: 0; color: var(--muted);
    cursor: pointer; padding: 2px 4px; font-size: 11px;
  }
  .strip-bar .toggle:hover { color: var(--text); }
  .strip-jobs { color: var(--accent); }
  .strip-bar .bulk-open { flex: none; padding: 4px 10px; font-size: 12px; }
  .pager { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); }
  .pager button { padding: 2px 8px; }

  .strip-scroll {
    display: flex; gap: 6px; padding: 0 10px 10px; overflow-x: auto;
    scrollbar-width: thin;
  }
  .thumb-wrap { position: relative; flex: none; }
  .thumb-wrap.busy .thumb img { opacity: 0.45; }
  .thumb-wrap .thumb { height: 66px; }
  .thumb-wrap.sel .thumb { outline: 2px solid var(--accent); outline-offset: -2px; border-color: var(--accent); }
  .thumb-wrap .pick {
    position: absolute; top: 3px; left: 3px; width: 15px; height: 15px; margin: 0;
    accent-color: var(--accent); cursor: pointer; z-index: 1;
    opacity: 0; transition: opacity 0.12s;
  }
  .thumb-wrap:hover .pick, .thumb-wrap.sel .pick, .thumb-wrap .pick:focus-visible { opacity: 1; }
  @media (prefers-reduced-motion: reduce) { .thumb-wrap .pick { transition: none; } }

  .thumb-spin {
    position: absolute; top: 50%; left: 50%; width: 16px; height: 16px;
    margin: -8px 0 0 -8px; border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.3); border-top-color: var(--accent);
    animation: thumb-spin 0.7s linear infinite;
  }
  @keyframes thumb-spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .thumb-spin { animation: none; } }

  .thumb {
    position: relative; display: block; flex: none;
    padding: 0; border: 1px solid var(--line); border-radius: 4px;
    background: var(--canvas-bg); cursor: pointer; aspect-ratio: 4 / 3; overflow: hidden;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb.on { outline: 2px solid var(--accent); border-color: var(--accent); }
  .edited {
    position: absolute; top: 3px; right: 3px; width: 7px; height: 7px;
    border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 1px #000;
  }

  /* --- Bulk-edit slide-over ------------------------------------------- */
  .sheet-scrim {
    position: fixed; inset: 0; z-index: 45; border: 0; padding: 0; border-radius: 0;
    background: rgba(0, 0, 0, 0.4); cursor: default;
  }
  .sheet {
    position: fixed; top: 0; right: 0; bottom: 0; z-index: 46;
    width: min(380px, 100%); display: flex; flex-direction: column;
    background: var(--panel); border-left: 1px solid var(--line);
    box-shadow: -12px 0 40px rgba(0, 0, 0, 0.4);
  }
  .sheet > header {
    flex: none; display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--line);
  }
  .sheet > header h2 {
    font-size: 14px; margin: 0; text-transform: none; letter-spacing: 0; color: var(--text);
  }
  .sheet .x { padding: 2px 9px; font-size: 17px; line-height: 1; }
  .sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px; }
  .sheet > footer {
    flex: none; display: flex; gap: 8px; justify-content: flex-end;
    padding: 12px 16px; border-top: 1px solid var(--line);
  }
  .sheet > footer .primary {
    background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600;
  }
  .sel-row {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    font-size: 12px; color: var(--muted); margin-bottom: 4px;
  }
  .sel-row .grow { flex: 1; }
  .sel-row button { padding: 4px 8px; font-size: 12px; }
  .area-modes {
    display: grid; gap: 10px; margin: 12px 0 0; padding: 12px 0 0;
    border: 0; border-top: 1px solid var(--line); min-width: 0;
  }
  .area-modes:disabled { opacity: 0.45; }
  .area-modes legend {
    padding: 0; font-size: var(--fs-eyebrow); text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted);
  }
  .area-modes label { display: flex; gap: 8px; align-items: flex-start; margin: 0; cursor: pointer; }
  .area-modes input { flex: none; width: auto; margin: 2px 0 0; accent-color: var(--accent); }
  .area-modes strong { display: block; font-size: 13px; color: var(--text); font-weight: 600; }
  .area-modes small { display: block; font-size: var(--fs-sm); color: var(--muted); line-height: 1.45; margin-top: 3px; }
  .linkish { background: transparent; border: 0; color: var(--accent); cursor: pointer; padding: 0; font-size: inherit; }
  aside {
    background: var(--panel); border-right: 1px solid var(--line);
    padding: 18px; min-height: 0; overflow-y: auto;
  }
  h2 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted); margin: 0 0 8px; }
  section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line); }
  section > :global(*) { margin-bottom: 8px; }

  .tabs {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 0;
    margin: 18px 0 0;
    border-bottom: 1px solid var(--line);
  }
  .tabs button {
    background: transparent; border: 0; border-radius: 0; padding: 10px 2px;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px;
    color: var(--muted); box-shadow: inset 0 -2px 0 transparent;
  }
  .tabs button:hover:not(:disabled) { border-color: transparent; color: var(--text); }
  .tabs button.active { color: var(--accent); box-shadow: inset 0 -2px 0 var(--accent); }
  .panel > section:first-child { margin-top: 14px; padding-top: 0; border-top: 0; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .check { display: flex; align-items: center; gap: 7px; color: var(--text); font-size: 13px; margin: 10px 0; }
  .check input { width: auto; accent-color: var(--accent); }
  .hint { font-size: 12.5px; color: var(--muted); line-height: 1.5; margin: 8px 0 0; }
  .actions { display: grid; gap: 8px; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; margin: 0; font-size: 13px; }
  dt { color: var(--muted); }
  dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }

  button.wide { width: 100%; }
  .rois { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 3px; }
  .rois li { display: grid; grid-template-columns: auto 1fr auto; align-items: center; border-radius: 5px; }
  .rois li.sel { outline: 1px solid var(--accent); }
  .swatch {
    position: relative; display: grid; place-items: center;
    padding: 5px 3px 5px 7px; cursor: pointer;
  }
  .swatch input[type="color"] {
    position: absolute; inset: 0; width: 100%; height: 100%;
    margin: 0; padding: 0; border: 0; opacity: 0; cursor: pointer;
  }
  .pick {
    display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 7px;
    text-align: left; font-size: 12.5px; padding: 5px 7px; background: transparent; border: 0;
  }
  .dot {
    width: 9px; height: 9px; border-radius: 50%;
    box-shadow: 0 0 0 1px var(--line-strong);
  }
  .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tm { color: var(--muted); font-variant-numeric: tabular-nums; }
  .del { background: transparent; border: 0; color: var(--muted); font-size: 15px; padding: 2px 7px; }
  .del:hover { color: #ff6b6b; }
  .detail { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line); }
  .detail > * { margin-bottom: 6px; }
  details summary { font-size: 12px; color: var(--muted); cursor: pointer; margin-top: 10px; }

  .advanced { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line); }
  .advanced > summary {
    margin: 0; list-style: none; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted);
  }
  .advanced > summary::-webkit-details-marker { display: none; }
  .advanced > summary::before { content: '▸'; font-size: 10px; }
  .advanced[open] > summary::before { content: '▾'; }
  .advanced > summary:hover { color: var(--text); }
  .adv { margin-top: 14px; }
  .adv + .adv { margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--line); }
  .adv > * { margin-bottom: 8px; }
  .adv h3 {
    font-size: var(--fs-eyebrow); text-transform: uppercase; letter-spacing: 0.6px;
    color: var(--muted); margin: 0 0 8px;
  }

  main { position: relative; min-height: 0; overflow: hidden; }
  .pane { position: absolute; inset: 0; }
  .pane.hidden { visibility: hidden; pointer-events: none; }

  .viewswitch {
    flex: none; display: inline-flex; gap: 2px; padding: 2px;
    background: var(--bg); border: 1px solid var(--line); border-radius: 8px;
  }
  .viewswitch button {
    display: inline-flex; align-items: center; gap: 6px;
    background: transparent; border: 0; border-radius: 6px;
    padding: 5px 12px; font-size: 12px; color: var(--muted);
  }
  .viewswitch button:hover:not(.on) { color: var(--text); }
  .viewswitch button.on { background: var(--accent); color: var(--on-accent); }
  .viewswitch .badge {
    font-size: 11px; font-variant-numeric: tabular-nums;
    padding: 0 5px; border-radius: 999px; line-height: 1.5;
    background: rgba(0, 0, 0, 0.18);
  }
  .viewswitch button:not(.on) .badge { background: var(--line); color: var(--text); }

  .empty {
    height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; color: var(--muted); text-align: center; padding: 24px;
  }
  .empty.big { gap: 14px; max-width: 460px; margin: 0 auto; }
  .empty.big h2 {
    font-size: 17px; color: var(--text); text-transform: none; letter-spacing: 0; margin: 0;
  }
  .empty.big p { margin: 0; font-size: 13px; line-height: 1.55; }
  .empty.big small { font-size: 12px; line-height: 1.5; }
  .empty-actions { display: flex; gap: 8px; margin-top: 2px; }
  .empty-actions .primary {
    background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600;
  }
</style>
