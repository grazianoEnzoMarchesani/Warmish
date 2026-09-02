<script lang="ts">
  /**
   * Pan/zoom canvas view with the interactive ROI layer — the Canvas2D
   * counterpart of QGraphicsView plus `ui/roi_items.py`.
   *
   * Qt dispatched press/move/release to whichever item was under the cursor.
   * There is no scene graph here, so this component owns one explicit state
   * machine: what the pointer grabbed on press decides what the drag means.
   */
  import { type CompositeResult } from '../core/render';
  import {
    nextRoiId, roiColor, roiContains, translateRoi,
    DEFAULT_ROI_EMISSIVITY, type Roi, type RoiStats,
  } from '../core/roi';
  import { drawRois, roiHandles, HANDLE_SIZE, type Affine, type RoiLabelSettings } from '../core/roiRender';
  import type { Tool } from './tools';

  interface Props {
    image: CompositeResult | null;
    rois: Roi[];
    stats: Map<string, RoiStats | null>;
    labels: RoiLabelSettings;
    tool: Tool;
    selectedId: string | null;
    onprobe?: (x: number, y: number) => void;
    /** Current zoom as a whole percentage, for the status bar. */
    onzoom?: (pct: number) => void;
    onselect?: (id: string | null) => void;
    /** Geometry changed by dragging; the parent recomputes statistics. */
    onroichange?: (roi: Roi) => void;
    onroicreate?: (roi: Roi) => void;
    ondelete?: (id: string) => void;
    ontoolreset?: () => void;
  }
  let {
    image, rois, stats, labels, tool, selectedId,
    onprobe, onzoom, onselect, onroichange, onroicreate, ondelete, ontoolreset,
  }: Props = $props();

  let canvas: HTMLCanvasElement;
  let host: HTMLDivElement;
  let scale = $state(1);
  let offset = $state({ x: 0, y: 0 });
  /** Sensor dimensions the current view was last fitted to, `''` before any fit. */
  let fittedSig = '';
  /** True once the user has zoomed or panned by hand — suppresses auto-fit until
   *  they ask for it again, so a palette tweak or a resize can't yank their view. */
  let userAdjusted = false;

  /** Draft geometry while a new ROI is being drawn. */
  let draft = $state<Roi | null>(null);
  let polyDraft = $state<[number, number][]>([]);
  let hotVertex = $state<number | null>(null);

  type Grab =
    | { kind: 'pan'; last: { x: number; y: number } }
    | { kind: 'move'; roi: Roi; last: { x: number; y: number }; moved: boolean }
    | { kind: 'handle'; roi: Roi; index: number; anchor: { x: number; y: number } }
    | { kind: 'draw'; start: { x: number; y: number } }
    | null;
  let grab: Grab = null;

  /** Sensor pixel → screen pixel, composing the overlay alignment with pan/zoom. */
  const toScreen = $derived<Affine>({
    scale: (image?.scale ?? 1) * scale,
    offsetX: (image?.offsetX ?? 0) * scale + offset.x,
    offsetY: (image?.offsetY ?? 0) * scale + offset.y,
  });

  export function fit(): void {
    if (!image || !host) return;
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (w < 1 || h < 1) return; // laid out to nothing yet — a resize will call back
    const k = Math.min(w / image.width, h / image.height) * 0.92;
    scale = k;
    offset = { x: (w - image.width * k) / 2, y: (h - image.height * k) / 2 };
    fittedSig = `${image.width}x${image.height}`;
    userAdjusted = false;
  }

  function draw(): void {
    if (!canvas || !host) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = host.clientWidth * dpr;
    canvas.height = host.clientHeight * dpr;
    canvas.style.width = `${host.clientWidth}px`;
    canvas.style.height = `${host.clientHeight}px`;
    const ctx = canvas.getContext('2d')!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, host.clientWidth, host.clientHeight);
    if (!image) return;

    ctx.imageSmoothingEnabled = scale < 3; // show the sensor grid when zoomed right in
    ctx.setTransform(scale * dpr, 0, 0, scale * dpr, offset.x * dpr, offset.y * dpr);
    ctx.drawImage(image.canvas, 0, 0);

    // ROIs are drawn in screen space so outlines and handles keep a constant
    // weight at any zoom, exactly as Qt's ItemIgnoresTransformations handles did.
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const live = draft ? [...rois, draft] : rois;
    if (live.length) {
      drawRois(ctx, {
        rois: live, stats, labels, transform: toScreen, selectedId, hotVertex,
        bounds: { width: host.clientWidth, height: host.clientHeight },
      });
    }
    if (polyDraft.length) drawPolyDraft(ctx);
  }

  function drawPolyDraft(ctx: CanvasRenderingContext2D): void {
    ctx.save();
    ctx.strokeStyle = '#ffb020';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    polyDraft.forEach(([px, py], i) => {
      const x = px * toScreen.scale + toScreen.offsetX;
      const y = py * toScreen.scale + toScreen.offsetY;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
    for (const [px, py] of polyDraft) {
      ctx.beginPath();
      ctx.arc(px * toScreen.scale + toScreen.offsetX, py * toScreen.scale + toScreen.offsetY, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#ffb020';
      ctx.fill();
    }
    ctx.restore();
  }

  $effect(() => {
    // Re-render whenever the composited image, the view transform or any ROI changes.
    void image; void scale; void offset;
    void rois; void stats; void Object.values(labels); void selectedId; void draft;
    void polyDraft; void hotVertex;
    draw();
  });

  $effect(() => {
    onzoom?.(Math.round(scale * 100));
  });

  $effect(() => {
    // Fit when a different frame is loaded (new dimensions), and keep a still-
    // fitted view fitted as the composite is rebuilt for a palette/range change.
    if (!image) return;
    if (`${image.width}x${image.height}` !== fittedSig || !userAdjusted) fit();
  });

  $effect(() => {
    // A resized viewport must re-fit, or the frame stays scaled to the old size
    // and only part of it shows. Once the user has zoomed by hand, leave it alone.
    const ro = new ResizeObserver(() => (userAdjusted ? draw() : fit()));
    ro.observe(host);
    return () => ro.disconnect();
  });

  /** Screen → sensor pixels, in floating point (ROIs are not grid-aligned). */
  function toImage(ev: PointerEvent | MouseEvent): { x: number; y: number } {
    const r = canvas.getBoundingClientRect();
    return {
      x: (ev.clientX - r.left - toScreen.offsetX) / toScreen.scale,
      y: (ev.clientY - r.top - toScreen.offsetY) / toScreen.scale,
    };
  }

  function screenPos(ev: PointerEvent | MouseEvent): { x: number; y: number } {
    const r = canvas.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }

  /** Handle under the cursor for the selected ROI, or -1. */
  function hitHandle(ev: PointerEvent): { roi: Roi; index: number } | null {
    const roi = rois.find((r) => r.id === selectedId);
    if (!roi) return null;
    const p = screenPos(ev);
    const half = HANDLE_SIZE / 2 + 2;
    const handles = roiHandles(roi, toScreen);
    for (let i = 0; i < handles.length; i++) {
      if (Math.abs(handles[i][0] - p.x) <= half && Math.abs(handles[i][1] - p.y) <= half) {
        return { roi, index: i };
      }
    }
    return null;
  }

  /** Topmost ROI containing the point; later ROIs win, matching their paint order. */
  function hitRoi(x: number, y: number): Roi | null {
    for (let i = rois.length - 1; i >= 0; i--) {
      if (roiContains(rois[i], x, y)) return rois[i];
    }
    return null;
  }

  function onwheel(ev: WheelEvent) {
    ev.preventDefault();
    const p = screenPos(ev);
    const k = Math.exp(-ev.deltaY * 0.0015);
    const next = Math.min(64, Math.max(0.05, scale * k));
    // Keep the point under the cursor anchored.
    offset = { x: p.x - (p.x - offset.x) * (next / scale), y: p.y - (p.y - offset.y) * (next / scale) };
    scale = next;
    userAdjusted = true;
  }

  function onpointerdown(ev: PointerEvent) {
    if (!image) return;
    canvas.setPointerCapture(ev.pointerId);
    const img = toImage(ev);

    if (tool === 'polygon') {
      polyDraft = [...polyDraft, [img.x, img.y]];
      return;
    }
    if (tool === 'rect' || tool === 'spot') {
      grab = { kind: 'draw', start: img };
      draft = tool === 'rect'
        ? { id: 'draft', type: 'RectROI', name: '', emissivity: DEFAULT_ROI_EMISSIVITY,
            color: roiColor(rois.length), x: img.x, y: img.y, width: 0, height: 0 }
        : { id: 'draft', type: 'SpotROI', name: '', emissivity: DEFAULT_ROI_EMISSIVITY,
            color: roiColor(rois.length), x: img.x, y: img.y, radius: 0 };
      return;
    }

    const handle = hitHandle(ev);
    if (handle) {
      hotVertex = handle.index;
      grab = { kind: 'handle', roi: handle.roi, index: handle.index, anchor: img };
      return;
    }

    const hit = hitRoi(img.x, img.y);
    if (hit) {
      if (hit.id !== selectedId) onselect?.(hit.id);
      grab = { kind: 'move', roi: hit, last: img, moved: false };
      return;
    }

    onselect?.(null);
    grab = { kind: 'pan', last: { x: ev.clientX, y: ev.clientY } };
  }

  function onpointermove(ev: PointerEvent) {
    if (!image) return;
    const img = toImage(ev);

    if (!grab) {
      onprobe?.(Math.floor(img.x), Math.floor(img.y));
      return;
    }

    if (grab.kind === 'pan') {
      offset = { x: offset.x + ev.clientX - grab.last.x, y: offset.y + ev.clientY - grab.last.y };
      grab.last = { x: ev.clientX, y: ev.clientY };
      userAdjusted = true;
      return;
    }

    if (grab.kind === 'move') {
      translateRoi(grab.roi, img.x - grab.last.x, img.y - grab.last.y);
      grab.last = img;
      grab.moved = true;
      onroichange?.(grab.roi);
      return;
    }

    if (grab.kind === 'handle') {
      resize(grab.roi, grab.index, img);
      onroichange?.(grab.roi);
      return;
    }

    if (grab.kind === 'draw' && draft) {
      if (draft.type === 'RectROI') {
        draft.x = Math.min(grab.start.x, img.x);
        draft.y = Math.min(grab.start.y, img.y);
        draft.width = Math.abs(img.x - grab.start.x);
        draft.height = Math.abs(img.y - grab.start.y);
      } else if (draft.type === 'SpotROI') {
        draft.radius = Math.hypot(img.x - grab.start.x, img.y - grab.start.y);
      }
      draft = { ...draft } as Roi; // re-trigger the render effect
    }
  }

  function resize(roi: Roi, index: number, p: { x: number; y: number }): void {
    if (roi.type === 'SpotROI') {
      roi.radius = Math.max(0.5, Math.hypot(p.x - roi.x, p.y - roi.y));
      return;
    }
    if (roi.type === 'PolygonROI') {
      roi.points[index] = [p.x, p.y];
      roi.points = [...roi.points];
      return;
    }
    // Rectangle: the grabbed corner follows the cursor, the opposite one is fixed.
    const x1 = roi.x, y1 = roi.y, x2 = roi.x + roi.width, y2 = roi.y + roi.height;
    const corners: [number, number][] = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
    const [ox, oy] = corners[(index + 2) % 4];
    roi.x = Math.min(ox, p.x);
    roi.y = Math.min(oy, p.y);
    roi.width = Math.abs(p.x - ox);
    roi.height = Math.abs(p.y - oy);
  }

  function onpointerup(ev: PointerEvent) {
    canvas.releasePointerCapture(ev.pointerId);
    hotVertex = null;

    if (grab?.kind === 'draw' && draft) {
      const created = finishDraft(draft);
      draft = null;
      grab = null;
      if (created) onroicreate?.(created);
      ontoolreset?.();
      return;
    }
    grab = null;
  }

  /** Rejects degenerate drags — a stray click should not leave a zero-size ROI. */
  function finishDraft(d: Roi): Roi | null {
    if (d.type === 'RectROI') {
      if (d.width < 1 || d.height < 1) return null;
      return { ...d, id: nextRoiId() };
    }
    // A plain click on the spot tool means "default radius here", not "radius 0".
    const radius = d.type === 'SpotROI' && d.radius < 1 ? 5 : (d as any).radius;
    return { ...d, id: nextRoiId(), radius } as Roi;
  }

  function ondblclick() {
    if (tool === 'polygon') closePolygon();
  }

  function closePolygon(): void {
    if (polyDraft.length >= 3) {
      onroicreate?.({
        id: nextRoiId(), type: 'PolygonROI', name: '', emissivity: DEFAULT_ROI_EMISSIVITY,
        color: roiColor(rois.length), points: polyDraft.map(([x, y]) => [x, y] as [number, number]),
      });
    }
    polyDraft = [];
    ontoolreset?.();
  }

  function onkeydown(ev: KeyboardEvent) {
    if (ev.key === 'Escape') {
      polyDraft = [];
      draft = null;
      grab = null;
      ontoolreset?.();
      onselect?.(null);
    } else if (ev.key === 'Enter' && tool === 'polygon') {
      closePolygon();
    } else if ((ev.key === 'Delete' || ev.key === 'Backspace') && selectedId) {
      ev.preventDefault();
      ondelete?.(selectedId);
    }
  }
</script>

<svelte:window onkeydown={onkeydown} />

<div class="host" bind:this={host}>
  <canvas
    bind:this={canvas}
    class:drawing={tool !== 'pan'}
    onwheel={onwheel}
    onpointerdown={onpointerdown}
    onpointermove={onpointermove}
    onpointerup={onpointerup}
    ondblclick={ondblclick}
    oncontextmenu={(e) => { e.preventDefault(); if (tool === 'polygon') closePolygon(); }}
    onpointerleave={() => onprobe?.(-1, -1)}
  ></canvas>
  {#if image && (tool === 'polygon' || tool === 'rect' || tool === 'spot')}
    <div class="hud">
      {#if tool === 'polygon'}clic: vertice · doppio clic o Invio: chiudi{/if}
      {#if tool === 'rect' || tool === 'spot'}trascina per disegnare{/if}
    </div>
  {/if}
</div>

<style>
  .host { position: relative; width: 100%; height: 100%; overflow: hidden; background: var(--canvas-bg); }
  canvas { display: block; touch-action: none; cursor: grab; }
  canvas:active { cursor: grabbing; }
  canvas.drawing, canvas.drawing:active { cursor: crosshair; }
  .hud {
    position: absolute; left: 12px; bottom: 12px; padding: 4px 8px;
    background: var(--overlay-bg); border: 1px solid var(--overlay-line); border-radius: 6px;
    box-shadow: var(--overlay-shadow); font-size: 12px; color: var(--overlay-fg-dim);
    backdrop-filter: blur(6px);
  }
</style>
