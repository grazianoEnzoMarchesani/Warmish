/**
 * Post-processing filters for the *visible* photo that sits under the thermal
 * overlay. These never touch the radiometric data — only the embedded JPEG the
 * camera stored alongside it.
 *
 * Two families live here:
 *   - a fast path that just hands Canvas2D a `filter` string (grayscale, sepia,
 *     contrast, blur, …);
 *   - a pixel path that walks an ImageData buffer (threshold, posterize,
 *     halftone, ordered dithering, Sobel edges, histogram equalisation, …).
 *
 * Everything is DOM-free — it goes through `createCanvas` / `context2d` from
 * render.ts — so the batch worker runs exactly the same code as the interactive
 * viewer. The module is deliberately *not* imported by render.ts: the callers
 * (App.svelte and pipeline.ts) filter the visible image before handing it to
 * `composite`, keeping render.ts pure geometry.
 */
import { context2d, createCanvas, type AnyCanvas, type Ctx2D } from './render';

export type FilterName =
  | 'none'
  | 'grayscale' | 'bw' | 'sepia' | 'invert' | 'contrast' | 'vivid' | 'warm' | 'cool'
  | 'blur' | 'sharpen' | 'edges' | 'emboss'
  | 'threshold' | 'posterize' | 'halftone' | 'dither' | 'duotone' | 'equalize'
  | 'pixelate' | 'vignette';

export interface VisibleFilter {
  name: FilterName;
  /** 0..100. Each filter maps this onto its own natural parameter. */
  strength: number;
}

interface FilterDef {
  name: FilterName;
  label: string;
  /** Strength applied when the filter is first chosen from the dropdown. */
  preset: number;
}

/** Dropdown order and Italian labels for the UI. */
export const FILTERS: FilterDef[] = [
  { name: 'none', label: 'Nessuno', preset: 50 },
  { name: 'grayscale', label: 'Bianco e nero', preset: 100 },
  { name: 'bw', label: 'B/N contrastato', preset: 55 },
  { name: 'sepia', label: 'Seppia', preset: 80 },
  { name: 'invert', label: 'Negativo', preset: 100 },
  { name: 'contrast', label: 'Contrasto', preset: 45 },
  { name: 'vivid', label: 'Colori vividi', preset: 45 },
  { name: 'warm', label: 'Viraggio caldo', preset: 55 },
  { name: 'cool', label: 'Viraggio freddo', preset: 55 },
  { name: 'blur', label: 'Sfocatura', preset: 30 },
  { name: 'sharpen', label: 'Nitidezza', preset: 55 },
  { name: 'edges', label: 'Contorni (Sobel)', preset: 55 },
  { name: 'emboss', label: 'Rilievo', preset: 55 },
  { name: 'threshold', label: 'Soglia (1 bit)', preset: 50 },
  { name: 'posterize', label: 'Posterizza', preset: 45 },
  { name: 'halftone', label: 'Mezzitoni', preset: 45 },
  { name: 'dither', label: 'Retino ordinato', preset: 50 },
  { name: 'duotone', label: 'Duotono', preset: 100 },
  { name: 'equalize', label: 'Equalizza istogramma', preset: 100 },
  { name: 'pixelate', label: 'Mosaico', preset: 40 },
  { name: 'vignette', label: 'Vignettatura', preset: 55 },
];

export const FILTER_NAMES: FilterName[] = FILTERS.map((f) => f.name);
export const DEFAULT_FILTER: VisibleFilter = { name: 'none', strength: 50 };

export function filterPreset(name: FilterName): number {
  return FILTERS.find((f) => f.name === name)?.preset ?? 50;
}

/** True when the filter would change nothing — lets callers skip the work. */
export function isIdentityFilter(f: VisibleFilter | null | undefined): boolean {
  return !f || f.name === 'none';
}

/** Filters expressible as a Canvas2D `filter` string, given strength `t` in 0..1. */
const CSS: Partial<Record<FilterName, (t: number) => string>> = {
  grayscale: (t) => `grayscale(${t})`,
  bw: (t) => `grayscale(1) contrast(${(1 + t * 2).toFixed(3)})`,
  sepia: (t) => `sepia(${t})`,
  invert: (t) => `invert(${t})`,
  contrast: (t) => `contrast(${(1 + t * 1.6).toFixed(3)})`,
  vivid: (t) => `saturate(${(1 + t * 2.2).toFixed(3)}) contrast(${(1 + t * 0.25).toFixed(3)})`,
  warm: (t) => `sepia(${(t * 0.55).toFixed(3)}) saturate(${(1 + t * 0.4).toFixed(3)}) hue-rotate(-${(t * 12).toFixed(1)}deg)`,
  cool: (t) => `saturate(${(1 + t * 0.25).toFixed(3)}) hue-rotate(${(t * 40).toFixed(1)}deg)`,
  blur: (t) => `blur(${(t * 6).toFixed(2)}px)`,
};

/**
 * Runs `filter` over `src` and returns a fresh canvas the same size. An identity
 * filter still copies, so callers can treat the result as owned; skip the call
 * with `isIdentityFilter` when that copy is not wanted.
 */
export function applyVisibleFilter(
  src: CanvasImageSource & { width: number; height: number },
  filter: VisibleFilter,
): AnyCanvas {
  const w = src.width | 0;
  const h = src.height | 0;
  const canvas = createCanvas(w, h);
  const ctx = context2d(canvas);
  const t = clamp01(filter.strength / 100);

  const css = CSS[filter.name];
  if (css) {
    ctx.filter = css(t);
    ctx.drawImage(src, 0, 0, w, h);
    ctx.filter = 'none';
    return canvas;
  }

  ctx.drawImage(src, 0, 0, w, h);
  if (filter.name === 'none') return canvas;

  const img = ctx.getImageData(0, 0, w, h);
  switch (filter.name) {
    case 'sharpen': convolve(img, sharpenKernel(t), 0); break;
    case 'emboss': emboss(img, t); break;
    case 'edges': sobel(img, t); break;
    case 'threshold': threshold(img, t); break;
    case 'posterize': posterize(img, t); break;
    case 'dither': dither(img, t); break;
    case 'duotone': duotone(img, t); break;
    case 'equalize': equalize(img, t); break;
    case 'halftone': halftone(ctx, img, w, h, t); return canvas;
    case 'pixelate': pixelate(ctx, img, w, h, t); return canvas;
    case 'vignette': ctx.putImageData(img, 0, 0); vignette(ctx, w, h, t); return canvas;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

// --- helpers ---------------------------------------------------------------

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);
const clamp255 = (v: number): number => (v < 0 ? 0 : v > 255 ? 255 : v);
const luma = (r: number, g: number, b: number): number => 0.299 * r + 0.587 * g + 0.114 * b;

function threshold(img: ImageData, t: number): void {
  const d = img.data;
  const cut = 40 + t * 175; // 0 → 40, 1 → 215
  for (let i = 0; i < d.length; i += 4) {
    const v = luma(d[i], d[i + 1], d[i + 2]) >= cut ? 255 : 0;
    d[i] = d[i + 1] = d[i + 2] = v;
  }
}

function posterize(img: ImageData, t: number): void {
  const d = img.data;
  const levels = Math.max(2, Math.round(8 - t * 6)); // 0 → 8 levels, 1 → 2
  const step = 255 / (levels - 1);
  for (let i = 0; i < d.length; i += 4) {
    d[i] = Math.round(d[i] / step) * step;
    d[i + 1] = Math.round(d[i + 1] / step) * step;
    d[i + 2] = Math.round(d[i + 2] / step) * step;
  }
}

const BAYER4 = [
  [0, 8, 2, 10],
  [12, 4, 14, 6],
  [3, 11, 1, 9],
  [15, 7, 13, 5],
];

function dither(img: ImageData, t: number): void {
  const { width: w, height: h, data: d } = img;
  const gamma = 1 + (t - 0.5) * 1.2; // strength tilts the mid-tones
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const v = Math.pow(luma(d[i], d[i + 1], d[i + 2]) / 255, gamma);
      const out = v > (BAYER4[y & 3][x & 3] + 0.5) / 16 ? 255 : 0;
      d[i] = d[i + 1] = d[i + 2] = out;
    }
  }
}

function duotone(img: ImageData, t: number): void {
  const d = img.data;
  const lo = [26, 32, 66]; // deep indigo shadows
  const hi = [255, 226, 186]; // warm paper highlights
  for (let i = 0; i < d.length; i += 4) {
    const k = luma(d[i], d[i + 1], d[i + 2]) / 255;
    for (let c = 0; c < 3; c++) {
      const mapped = lo[c] + (hi[c] - lo[c]) * k;
      d[i + c] = clamp255(d[i + c] + (mapped - d[i + c]) * t);
    }
  }
}

/** Global histogram equalisation on luminance, applied as a per-pixel gain. */
function equalize(img: ImageData, t: number): void {
  const d = img.data;
  const hist = new Float64Array(256);
  for (let i = 0; i < d.length; i += 4) hist[Math.round(luma(d[i], d[i + 1], d[i + 2]))]++;
  const total = d.length / 4 || 1;
  const map = new Float64Array(256);
  let acc = 0;
  for (let k = 0; k < 256; k++) {
    acc += hist[k];
    map[k] = (acc / total) * 255;
  }
  for (let i = 0; i < d.length; i += 4) {
    const l = luma(d[i], d[i + 1], d[i + 2]);
    if (l < 1) continue;
    const gain = map[Math.round(l)] / l;
    for (let c = 0; c < 3; c++) d[i + c] = clamp255(d[i + c] * (1 - t) + d[i + c] * gain * t);
  }
}

/** Generic 3×3 convolution with edge clamping; reads from a copy, writes RGB. */
function convolve(img: ImageData, k: number[], bias: number): void {
  const { width: w, height: h, data: d } = img;
  const src = new Uint8ClampedArray(d);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let r = 0, g = 0, b = 0;
      for (let ky = -1; ky <= 1; ky++) {
        const yy = Math.min(h - 1, Math.max(0, y + ky));
        for (let kx = -1; kx <= 1; kx++) {
          const xx = Math.min(w - 1, Math.max(0, x + kx));
          const kv = k[(ky + 1) * 3 + (kx + 1)];
          const j = (yy * w + xx) * 4;
          r += src[j] * kv;
          g += src[j + 1] * kv;
          b += src[j + 2] * kv;
        }
      }
      const i = (y * w + x) * 4;
      d[i] = clamp255(r + bias);
      d[i + 1] = clamp255(g + bias);
      d[i + 2] = clamp255(b + bias);
    }
  }
}

function sharpenKernel(t: number): number[] {
  const a = t * 1.4;
  return [0, -a, 0, -a, 1 + 4 * a, -a, 0, -a, 0];
}

function emboss(img: ImageData, t: number): void {
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = luma(d[i], d[i + 1], d[i + 2]);
    d[i] = d[i + 1] = d[i + 2] = v; // grey first, so the relief isn't tinted
  }
  const a = 0.5 + t * 1.5;
  convolve(img, [-a, -a, 0, -a, 1, a, 0, a, a], 128);
}

/** Sobel gradient magnitude, painted white-on-black. */
function sobel(img: ImageData, t: number): void {
  const { width: w, height: h, data: d } = img;
  const g = new Float32Array(w * h);
  for (let i = 0, j = 0; i < d.length; i += 4, j++) g[j] = luma(d[i], d[i + 1], d[i + 2]);
  const gain = (0.4 + t * 2.5) * 0.25;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const x0 = Math.max(0, x - 1), x1 = Math.min(w - 1, x + 1);
      const y0 = Math.max(0, y - 1), y1 = Math.min(h - 1, y + 1);
      const tl = g[y0 * w + x0], tc = g[y0 * w + x], tr = g[y0 * w + x1];
      const ml = g[y * w + x0], mr = g[y * w + x1];
      const bl = g[y1 * w + x0], bc = g[y1 * w + x], br = g[y1 * w + x1];
      const gx = tr + 2 * mr + br - (tl + 2 * ml + bl);
      const gy = bl + 2 * bc + br - (tl + 2 * tc + tr);
      const mag = clamp255(Math.hypot(gx, gy) * gain);
      const i = (y * w + x) * 4;
      d[i] = d[i + 1] = d[i + 2] = mag;
    }
  }
}

function halftone(ctx: Ctx2D, img: ImageData, w: number, h: number, t: number): void {
  const d = img.data;
  const cell = Math.round(4 + t * 16);
  ctx.save();
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#111';
  for (let cy = 0; cy < h; cy += cell) {
    for (let cx = 0; cx < w; cx += cell) {
      let sum = 0, n = 0;
      const ey = Math.min(h, cy + cell), ex = Math.min(w, cx + cell);
      for (let y = cy; y < ey; y++) {
        for (let x = cx; x < ex; x++) {
          const i = (y * w + x) * 4;
          sum += luma(d[i], d[i + 1], d[i + 2]);
          n++;
        }
      }
      const darkness = 1 - sum / (n * 255);
      const r = Math.sqrt(darkness) * cell * 0.72;
      if (r > 0.3) {
        ctx.beginPath();
        ctx.arc(cx + cell / 2, cy + cell / 2, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.restore();
}

function pixelate(ctx: Ctx2D, img: ImageData, w: number, h: number, t: number): void {
  const d = img.data;
  const block = Math.round(2 + t * 34);
  for (let by = 0; by < h; by += block) {
    for (let bx = 0; bx < w; bx += block) {
      let r = 0, g = 0, b = 0, n = 0;
      const ey = Math.min(h, by + block), ex = Math.min(w, bx + block);
      for (let y = by; y < ey; y++) {
        for (let x = bx; x < ex; x++) {
          const i = (y * w + x) * 4;
          r += d[i];
          g += d[i + 1];
          b += d[i + 2];
          n++;
        }
      }
      ctx.fillStyle = `rgb(${(r / n) | 0},${(g / n) | 0},${(b / n) | 0})`;
      ctx.fillRect(bx, by, ex - bx, ey - by);
    }
  }
}

function vignette(ctx: Ctx2D, w: number, h: number, t: number): void {
  const cx = w / 2, cy = h / 2;
  const outer = Math.hypot(cx, cy);
  const grad = ctx.createRadialGradient(cx, cy, outer * 0.35, cx, cy, outer);
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, `rgba(0,0,0,${(0.15 + t * 0.75).toFixed(3)})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}
