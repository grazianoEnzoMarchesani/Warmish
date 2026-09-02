/**
 * Compositing of the thermal layer over the embedded visible image, mirroring
 * ui/widgets/image_graphics_view.py. Qt's CompositionMode names map 1:1 onto
 * Canvas2D globalCompositeOperation.
 */
export const BLEND_MODES = {
  Normal: 'source-over',
  Multiply: 'multiply',
  Screen: 'screen',
  Overlay: 'overlay',
  Darken: 'darken',
  Lighten: 'lighten',
  ColorDodge: 'color-dodge',
  ColorBurn: 'color-burn',
  HardLight: 'hard-light',
  SoftLight: 'soft-light',
  Difference: 'difference',
  Exclusion: 'exclusion',
  Plus: 'lighter',
} as const;

export type BlendMode = keyof typeof BLEND_MODES;
export const BLEND_NAMES = Object.keys(BLEND_MODES) as BlendMode[];

/**
 * Batch processing runs this same code inside a Web Worker, where `document`
 * does not exist — hence the canvas abstraction rather than a second renderer
 * that could drift from the interactive one.
 */
export type AnyCanvas = HTMLCanvasElement | OffscreenCanvas;
export type Ctx2D = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

export function createCanvas(width: number, height: number): AnyCanvas {
  if (typeof document === 'undefined') return new OffscreenCanvas(width, height);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

export function context2d(canvas: AnyCanvas): Ctx2D {
  return canvas.getContext('2d') as Ctx2D;
}

/** PNG encoding, whichever canvas flavour produced the pixels. */
export function canvasToPng(canvas: AnyCanvas): Promise<Blob> {
  if ('convertToBlob' in canvas) return canvas.convertToBlob({ type: 'image/png' });
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG encoding failed'))), 'image/png');
  });
}

/** JPEG encoding — for large on-screen previews (the map tour) where a decorated
 *  PNG would be several megabytes for no visible gain. */
export function canvasToJpeg(canvas: AnyCanvas, quality = 0.85): Promise<Blob> {
  if ('convertToBlob' in canvas) return canvas.convertToBlob({ type: 'image/jpeg', quality });
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('JPEG encoding failed'))), 'image/jpeg', quality);
  });
}

export function imageDataToCanvas(pixels: Uint8ClampedArray, width: number, height: number): AnyCanvas {
  const canvas = createCanvas(width, height);
  context2d(canvas).putImageData(new ImageData(pixels, width, height), 0, 0);
  return canvas;
}

export interface OverlayAlignment {
  /** User scale of the thermal layer relative to its natural fit, 0.1..5. */
  scale: number;
  /** Thermal offset in **visible-image pixels**, as the sidecar stores it. */
  offsetX: number;
  offsetY: number;
}

export const DEFAULT_ALIGNMENT: OverlayAlignment = { scale: 1, offsetX: 0, offsetY: 0 };

/**
 * Overlay alignment as the camera recorded it, mirroring the desktop's
 * `get_overlay_parameters_from_metadata`: scale is `1 / Real2IR`, the offsets are
 * taken verbatim (they are already in visible-image pixels). Used as the starting
 * alignment on open and as the target of "reset alignment".
 */
export function alignmentFromMetadata(m: { Real2IR: number; OffsetX: number; OffsetY: number }): OverlayAlignment {
  const scale = m.Real2IR > 0 ? 1 / m.Real2IR : 1;
  return { scale: clamp(scale, 0.1, 5), offsetX: m.OffsetX, offsetY: m.OffsetY };
}

export interface CompositeOptions {
  thermal: CanvasImageSource;
  width: number;
  height: number;
  visible: (CanvasImageSource & { width: number; height: number }) | null;
  blend: BlendMode;
  /** Thermal layer opacity, 0..1. Only meaningful when a visible image exists. */
  opacity: number;
  alignment?: OverlayAlignment;
}

export interface CompositeResult {
  canvas: AnyCanvas;
  width: number;
  height: number;
  /** Sensor pixel → view pixel: `view = thermal * scale + offset`. */
  scale: number;
  offsetX: number;
  offsetY: number;
}

/**
 * Flattens thermal over visible, mirroring `_update_overlay_positioning`.
 *
 * Without an overlay the view *is* the thermal frame. With one, the visible
 * image becomes the frame (that is where the desktop's offsets are measured),
 * the thermal layer is scaled by `alignment.scale × natural fit`, centred, and
 * shifted by the offsets. The returned transform is what maps a sensor pixel
 * into the produced canvas — the probe, the ROI layer and the exporters all
 * rely on it rather than re-deriving the geometry.
 */
export function composite(o: CompositeOptions): CompositeResult {
  if (!o.visible) {
    const canvas = createCanvas(o.width, o.height);
    context2d(canvas).drawImage(o.thermal, 0, 0, o.width, o.height);
    return { canvas, width: o.width, height: o.height, scale: 1, offsetX: 0, offsetY: 0 };
  }

  const a = o.alignment ?? DEFAULT_ALIGNMENT;
  const vw = o.visible.width;
  const vh = o.visible.height;
  const natural = Math.min(vw / o.width, vh / o.height);
  const scale = clamp(a.scale, 0.1, 5) * natural;
  const offsetX = (vw - o.width * scale) / 2 + a.offsetX;
  const offsetY = (vh - o.height * scale) / 2 + a.offsetY;

  const canvas = createCanvas(vw, vh);
  const c = context2d(canvas);
  c.drawImage(o.visible, 0, 0);
  c.globalCompositeOperation = BLEND_MODES[o.blend];
  c.globalAlpha = o.opacity;
  c.drawImage(o.thermal, offsetX, offsetY, o.width * scale, o.height * scale);
  c.globalCompositeOperation = 'source-over';
  c.globalAlpha = 1;

  return { canvas, width: vw, height: vh, scale, offsetX, offsetY };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Vertical colour bar with min/max labels, the web counterpart of color_bar_legend.py. */
export function drawLegend(
  ctx: Ctx2D,
  lut: Uint8Array,
  inverted: boolean,
  min: number,
  max: number,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  for (let i = 0; i < h; i++) {
    const t = 1 - i / (h - 1);
    let idx = Math.floor((inverted ? 1 - t : t) * 256);
    idx = Math.min(255, Math.max(0, idx));
    ctx.fillStyle = `rgb(${lut[idx * 3]},${lut[idx * 3 + 1]},${lut[idx * 3 + 2]})`;
    ctx.fillRect(x, y + i, w, 1);
  }
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.strokeRect(x + 0.5, y + 0.5, w, h);

  ctx.fillStyle = '#fff';
  ctx.font = '12px system-ui, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const label = (v: number) => `${v.toFixed(1)} °C`;
  ctx.fillText(label(max), x + w + 6, y + 6);
  ctx.fillText(label(min), x + w + 6, y + h - 6);
}

/**
 * Horizontal colour bar used at the bottom of the exported PNGs, stacked as
 * (optional) temperature histogram on top, the colour bar in the middle, and
 * the min/mid/max labels underneath — the flat counterpart of the in-canvas
 * range scale. `min` is on the left, `max` on the right; `k` scales the text
 * and padding so it stays legible whatever the output resolution.
 *
 * `histogram` holds bin counts, coldest first, spanning `[min, max]`; its
 * orientation never flips with `inverted` (only the gradient does).
 */
export function drawLegendH(
  ctx: Ctx2D,
  lut: Uint8Array,
  inverted: boolean,
  min: number,
  max: number,
  x: number,
  y: number,
  w: number,
  h: number,
  k = 1,
  histogram?: number[],
): void {
  const font = Math.round(12 * k);
  const pad = Math.round(10 * k);
  const gap = Math.round(6 * k);
  const histH = histogram && histogram.length ? Math.round(24 * k) : 0;
  const barH = Math.max(6, h - font - gap - (histH ? histH + gap : 0));
  const barY = y + (histH ? histH + gap : 0);
  const textY = barY + barH + gap + font;

  if (histH) {
    const n = histogram!.length;
    const peak = Math.max(1, ...histogram!);
    const base = barY - gap;
    ctx.beginPath();
    ctx.moveTo(x, base);
    for (let i = 0; i < n; i++) {
      ctx.lineTo(x + ((i + 0.5) / n) * w, base - (histogram![i] / peak) * histH);
    }
    ctx.lineTo(x + w, base);
    ctx.closePath();
    ctx.fillStyle = 'rgba(230,232,236,0.24)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(230,232,236,0.65)';
    ctx.lineWidth = Math.max(1, k);
    ctx.stroke();
  }

  for (let i = 0; i < w; i++) {
    const t = i / (w - 1);
    let idx = Math.floor((inverted ? 1 - t : t) * 256);
    idx = Math.min(255, Math.max(0, idx));
    ctx.fillStyle = `rgb(${lut[idx * 3]},${lut[idx * 3 + 1]},${lut[idx * 3 + 2]})`;
    ctx.fillRect(x + i, barY, 1, barH);
  }
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.strokeRect(x + 0.5, barY + 0.5, w - 1, barH - 1);

  ctx.fillStyle = '#fff';
  ctx.font = `${font}px system-ui, sans-serif`;
  ctx.textBaseline = 'alphabetic';
  const mid = (min + max) / 2;
  ctx.textAlign = 'left';
  ctx.fillText(`${min.toFixed(1)} °C`, x + pad, textY);
  ctx.textAlign = 'center';
  ctx.fillText(`${mid.toFixed(1)} °C`, x + w / 2, textY);
  ctx.textAlign = 'right';
  ctx.fillText(`${max.toFixed(1)} °C`, x + w - pad, textY);
  ctx.textAlign = 'left';
}
