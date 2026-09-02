/**
 * ROI drawing — the Canvas2D counterpart of `ui/roi_items.py`.
 *
 * Qt hands each item its own coordinate system; here there is one canvas, so
 * every routine takes the affine that maps a sensor pixel into the target
 * canvas (`view = thermal * scale + offset`) and draws in canvas coordinates.
 * The same code paints the live viewer and the burnt-in PNG export, which is
 * why handle drawing is opt-in rather than implicit.
 *
 * Labels are "connected callouts": a small card that lives OUTSIDE the ROI,
 * tied to it by a thin leader line to the ROI centre. A layout pass places
 * every card before any is drawn, so that no two cards overlap and no card
 * covers a ROI or leaves the picture — see `layoutLabels`.
 */
import type { Roi, RoiStats } from './roi';
import { roiBounds } from './roi';
import type { Ctx2D } from './render';

export interface Affine { scale: number; offsetX: number; offsetY: number }

export interface RoiLabelSettings {
  name: boolean;
  emissivity: boolean;
  min: boolean;
  max: boolean;
  avg: boolean;
  median: boolean;
  /** Multiplies label card text and padding only (not ROI strokes/handles). */
  scale: number;
}

export const DEFAULT_LABEL_SETTINGS: RoiLabelSettings = {
  name: true, emissivity: true, min: true, max: true, avg: true, median: false, scale: 1,
};

export const LABEL_SCALE_MIN = 0.6;
export const LABEL_SCALE_MAX = 2.5;

const labelScale = (s: RoiLabelSettings): number =>
  clamp(Number.isFinite(s.scale) ? s.scale : 1, LABEL_SCALE_MIN, LABEL_SCALE_MAX);

export interface DrawRoisOptions {
  rois: Roi[];
  stats: Map<string, RoiStats | null>;
  labels: RoiLabelSettings;
  transform: Affine;
  /** Multiplies strokes, handles and text so they stay legible at any output size. */
  uiScale?: number;
  /** Draws selection handles for this ROI; omit for exports. */
  selectedId?: string | null;
  /** Vertex index highlighted while dragging, polygons only. */
  hotVertex?: number | null;
  /**
   * Drawing area in the ctx's own units, used to keep labels on screen.
   * Defaults to the backing canvas, which is only right when no device-pixel
   * transform is in play — the viewer passes its CSS size instead.
   */
  bounds?: { width: number; height: number };
}

export const HANDLE_SIZE = 10;

const NAME_COLOR = '#ff8a3d';
const KEY_COLOR = '#7f8894';
const VAL_COLOR = '#d7dbe1';
const EPS_COLOR = '#9aa2ae';
const CARD_BG = 'rgba(9, 11, 15, 0.9)';

const to = (t: Affine, x: number, y: number): [number, number] => [x * t.scale + t.offsetX, y * t.scale + t.offsetY];

/** Traces a ROI outline in canvas coordinates; the caller strokes or fills it. */
export function roiPath(ctx: Ctx2D | Path2D, roi: Roi, t: Affine): void {
  const path = ctx as Path2D & CanvasRenderingContext2D;
  if (roi.type === 'RectROI') {
    const [x, y] = to(t, roi.x, roi.y);
    path.rect(x, y, roi.width * t.scale, roi.height * t.scale);
  } else if (roi.type === 'SpotROI') {
    const [x, y] = to(t, roi.x, roi.y);
    path.moveTo(x + roi.radius * t.scale, y);
    path.arc(x, y, roi.radius * t.scale, 0, Math.PI * 2);
  } else {
    roi.points.forEach(([px, py], i) => {
      const [x, y] = to(t, px, py);
      if (i === 0) path.moveTo(x, y);
      else path.lineTo(x, y);
    });
    if (roi.points.length > 2) path.closePath();
  }
}

/** Handle centres in canvas coordinates, in the order the hit test expects. */
export function roiHandles(roi: Roi, t: Affine): [number, number][] {
  if (roi.type === 'RectROI') {
    const [x1, y1, x2, y2] = roiBounds(roi);
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]].map(([x, y]) => to(t, x, y));
  }
  if (roi.type === 'SpotROI') return [to(t, roi.x + roi.radius, roi.y)];
  return roi.points.map(([x, y]) => to(t, x, y));
}

export function drawRois(ctx: Ctx2D, o: DrawRoisOptions): void {
  const k = o.uiScale ?? 1;
  const t = o.transform;
  const bounds = o.bounds ?? { width: ctx.canvas.width, height: ctx.canvas.height };
  ctx.save();
  ctx.lineJoin = 'round';

  // Screen-space bounding box of every ROI, reused by the label layout so a
  // card never lands on a ROI (its own or a neighbour's).
  const roiRects = o.rois.map((r) => screenRect(r, t));

  for (let i = 0; i < o.rois.length; i++) {
    const roi = o.rois[i];
    const selected = roi.id === o.selectedId;
    const path = new Path2D();
    roiPath(path, roi, t);

    ctx.fillStyle = withAlpha(roi.color, selected ? 0.24 : 0.16);
    ctx.fill(path);
    ctx.strokeStyle = roi.color;
    ctx.lineWidth = (selected ? 2.5 : 1.8) * k;
    ctx.stroke(path);

    if (roi.type === 'SpotROI') {
      // A crosshair marks the exact centre, which the circle alone does not show.
      const [cx, cy] = to(t, roi.x, roi.y);
      const r = 4 * k;
      ctx.beginPath();
      ctx.moveTo(cx - r, cy); ctx.lineTo(cx + r, cy);
      ctx.moveTo(cx, cy - r); ctx.lineTo(cx, cy + r);
      ctx.lineWidth = 1.2 * k;
      ctx.stroke();
    }
  }

  // Place every label first, then paint — the selected card last so its ring
  // and shadow sit above its neighbours.
  const models = layoutLabels(ctx, o, k, roiRects, bounds);
  const ordered = [
    ...models.filter((m) => m.roi.id !== o.selectedId),
    ...models.filter((m) => m.roi.id === o.selectedId),
  ];
  for (const m of ordered) drawCard(ctx, m, k, m.roi.id === o.selectedId);

  for (let i = 0; i < o.rois.length; i++) {
    if (o.rois[i].id === o.selectedId) drawHandles(ctx, o.rois[i], t, k, o.hotVertex ?? null);
  }
  ctx.restore();
}

function drawHandles(ctx: Ctx2D, roi: Roi, t: Affine, k: number, hot: number | null): void {
  const size = HANDLE_SIZE * k;
  roiHandles(roi, t).forEach(([x, y], i) => {
    ctx.beginPath();
    if (roi.type === 'SpotROI') ctx.arc(x, y, size / 2, 0, Math.PI * 2);
    else ctx.rect(x - size / 2, y - size / 2, size, size);
    ctx.fillStyle = i === hot ? 'rgba(255,150,0,0.86)' : 'rgba(100,150,255,0.7)';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1 * k;
    ctx.stroke();
  });
}

// ---------------------------------------------------------------------------
// Labels: connected callouts with non-overlapping placement
// ---------------------------------------------------------------------------

interface Rect { x: number; y: number; w: number; h: number }

interface ScreenRect extends Rect { cx: number; cy: number }

interface LabelCol { key: string; val: string }

interface LabelModel {
  roi: Roi;
  color: string;
  /** First line: ROI name (bold) and/or emissivity. */
  l1: { name: string; eps: string } | null;
  cols: LabelCol[];
  centroid: [number, number];
  spine: number;
  /** Effective label scale (uiScale × user label-size slider). */
  lk: number;
  w: number;
  h: number;
  /** Measured sub-metrics reused by the draw pass. */
  lay: {
    px: number; py: number; l1h: number; l1Gap: number; rowGap: number;
    keyFont: number; colGap: number; colW: number[];
  };
  /** Filled by `layoutLabels`. */
  rect: Rect;
}

/** Screen-space bounding box (plus centre) of a ROI. */
function screenRect(roi: Roi, t: Affine): ScreenRect {
  const [bx1, by1, bx2, by2] = roiBounds(roi);
  const [sx1, sy1] = to(t, bx1, by1);
  const [sx2, sy2] = to(t, bx2, by2);
  const x = Math.min(sx1, sx2), y = Math.min(sy1, sy2);
  const w = Math.abs(sx2 - sx1), h = Math.abs(sy2 - sy1);
  return { x, y, w, h, cx: x + w / 2, cy: y + h / 2 };
}

const fmtStat = (v: number | undefined) =>
  v === undefined || !Number.isFinite(v) ? 'N/A' : v.toFixed(2);

/**
 * Builds the label for one ROI at a given detail level:
 * 0 = every enabled field, 1 = first line + a single value, 2 = first line only.
 * Returns null when nothing is enabled at that level.
 */
function buildModel(
  ctx: Ctx2D, roi: Roi, stats: RoiStats | null, s: RoiLabelSettings, level: number, k0: number,
): LabelModel | null {
  const k = k0 * labelScale(s);
  const name = s.name ? roi.name : '';
  const eps = s.emissivity ? `ε ${roi.emissivity.toFixed(3)}` : '';
  const l1 = name || eps ? { name, eps } : null;

  const all: LabelCol[] = [];
  if (s.min) all.push({ key: 'MIN', val: fmtStat(stats?.min) });
  if (s.max) all.push({ key: 'MAX', val: fmtStat(stats?.max) });
  if (s.avg) all.push({ key: 'MEAN', val: fmtStat(stats?.mean) });
  if (s.median) all.push({ key: 'MEDIAN', val: fmtStat(stats?.median) });

  let cols: LabelCol[];
  if (level <= 0) cols = all;
  else if (level === 1) {
    const pick = all.find((c) => c.key === 'MAX') ?? all[0];
    cols = pick ? [pick] : [];
  } else cols = [];

  if (!l1 && !cols.length) return null;

  const px = 7 * k, py = 5 * k, l1Gap = 4 * k, rowGap = 3 * k, colGap = 10 * k;
  const nameFont = `600 ${12 * k}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
  const epsFont = `${11 * k}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
  const keyFont = 8.5 * k;
  const keyFontStr = `${keyFont}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
  const valFont = `${11 * k}px ui-monospace, SFMono-Regular, Menlo, monospace`;

  let l1w = 0;
  if (l1) {
    if (l1.name) { ctx.font = nameFont; l1w += ctx.measureText(l1.name).width; }
    if (l1.eps) { ctx.font = epsFont; l1w += ctx.measureText((l1.name ? ' ' : '') + l1.eps).width; }
  }

  const colW: number[] = [];
  let gridW = 0;
  cols.forEach((c, i) => {
    ctx.font = keyFontStr;
    const kw = ctx.measureText(c.key).width;
    ctx.font = valFont;
    const vw = ctx.measureText(c.val).width;
    const cw = Math.max(kw, vw);
    colW.push(cw);
    gridW += cw + (i ? colGap : 0);
  });

  const spine = 3 * k;
  const l1h = l1 ? 14 * k : 0;
  const gridH = cols.length ? keyFont + rowGap + 12 * k : 0;
  const contentW = Math.max(l1w, gridW);

  return {
    roi,
    color: roi.color,
    l1,
    cols,
    centroid: [0, 0],
    spine,
    lk: k,
    w: spine + px * 2 + contentW,
    h: py * 2 + l1h + (l1h && gridH ? l1Gap : 0) + gridH,
    lay: { px, py, l1h, l1Gap, rowGap, keyFont, colGap, colW },
    rect: { x: 0, y: 0, w: 0, h: 0 },
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

function overlaps(a: Rect, b: Rect, margin: number): boolean {
  return a.x < b.x + b.w + margin && a.x + a.w + margin > b.x
    && a.y < b.y + b.h + margin && a.y + a.h + margin > b.y;
}

function insideCanvas(r: Rect, b: { width: number; height: number }): boolean {
  return r.x >= 0 && r.y >= 0 && r.x + r.w <= b.width && r.y + r.h <= b.height;
}

/** Candidate top-left positions around a ROI, ring 0 hugging it, further out after. */
function candidatePositions(w: number, h: number, rr: ScreenRect, ring: number, k: number): Rect[] {
  const g = 6 * k + ring * 18 * k;
  const x2 = rr.x + rr.w, y2 = rr.y + rr.h;
  const at = (x: number, y: number): Rect => ({ x, y, w, h });
  return [
    at(rr.x - w - g, rr.y - h - g),   // NW  — the historical default
    at(rr.cx - w / 2, rr.y - h - g),  // N
    at(x2 + g, rr.y - h - g),         // NE
    at(x2 + g, rr.cy - h / 2),        // E
    at(x2 + g, y2 + g),              // SE
    at(rr.cx - w / 2, y2 + g),        // S
    at(rr.x - w - g, y2 + g),         // SW
    at(rr.x - w - g, rr.cy - h / 2),  // W
  ];
}

/**
 * Places every label so no two cards overlap and no card covers a ROI or falls
 * outside the picture. Cards are tried at full detail first, then trimmed; a ROI
 * whose card fits nowhere keeps the full card clamped into view as a last resort.
 */
function layoutLabels(
  ctx: Ctx2D, o: DrawRoisOptions, k: number, roiRects: ScreenRect[],
  bounds: { width: number; height: number },
): LabelModel[] {
  const placed: Rect[] = [];
  const out: LabelModel[] = [];
  const cardMargin = 5 * k;
  const roiMargin = 1 * k;

  for (let i = 0; i < o.rois.length; i++) {
    const roi = o.rois[i];
    const rr = roiRects[i];
    const others = roiRects.filter((_, j) => j !== i);
    let chosen: LabelModel | null = null;

    for (let level = 0; level <= 2 && !chosen; level++) {
      const m = buildModel(ctx, roi, o.stats.get(roi.id) ?? null, o.labels, level, k);
      if (!m) continue;
      for (let ring = 0; ring <= 6 && !chosen; ring++) {
        for (const cand of candidatePositions(m.w, m.h, rr, ring, k)) {
          if (!insideCanvas(cand, bounds)) continue;
          if (placed.some((p) => overlaps(cand, p, cardMargin))) continue;
          if (others.some((r) => overlaps(cand, r, roiMargin))) continue;
          m.rect = cand;
          m.centroid = [clamp(rr.cx, 0, bounds.width), clamp(rr.cy, 0, bounds.height)];
          chosen = m;
          break;
        }
      }
    }

    if (!chosen) {
      const full = buildModel(ctx, roi, o.stats.get(roi.id) ?? null, o.labels, 2, k)
        ?? buildModel(ctx, roi, o.stats.get(roi.id) ?? null, o.labels, 1, k)
        ?? buildModel(ctx, roi, o.stats.get(roi.id) ?? null, o.labels, 0, k);
      if (!full) continue;
      full.centroid = [clamp(rr.cx, 0, bounds.width), clamp(rr.cy, 0, bounds.height)];
      // No spot around the ROI worked — sweep the whole picture for any free
      // slot before giving up and letting the card overlap.
      const stepX = Math.max(24 * k, full.w / 2);
      const stepY = Math.max(16 * k, full.h / 2);
      let swept: Rect | null = null;
      for (let gy = 0; gy + full.h <= bounds.height && !swept; gy += stepY) {
        for (let gx = 0; gx + full.w <= bounds.width && !swept; gx += stepX) {
          const cand = { x: gx, y: gy, w: full.w, h: full.h };
          if (placed.some((p) => overlaps(cand, p, cardMargin))) continue;
          if (others.some((r) => overlaps(cand, r, roiMargin))) continue;
          swept = cand;
        }
      }
      const g = 6 * k;
      full.rect = swept ?? {
        x: clamp(rr.x - full.w - g, 0, Math.max(0, bounds.width - full.w)),
        y: clamp(rr.y - full.h - g, 0, Math.max(0, bounds.height - full.h)),
        w: full.w, h: full.h,
      };
      chosen = full;
    }

    placed.push(chosen.rect);
    out.push(chosen);
  }
  return out;
}

function roundRectPath(ctx: Ctx2D, x: number, y: number, w: number, h: number, r: number): void {
  const rad = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rad, y);
  ctx.arcTo(x + w, y, x + w, y + h, rad);
  ctx.arcTo(x + w, y + h, x, y + h, rad);
  ctx.arcTo(x, y + h, x, y, rad);
  ctx.arcTo(x, y, x + w, y, rad);
  ctx.closePath();
}

function drawCard(ctx: Ctx2D, m: LabelModel, k: number, selected: boolean): void {
  const { x, y, w, h } = m.rect;
  const [cx, cy] = m.centroid;

  // Leader line from the ROI centre to the nearest point of the card, then a
  // dot on the centre — the only marks the callout adds to the picture.
  const nx = clamp(cx, x, x + w);
  const ny = clamp(cy, y, y + h);
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nx, ny);
  ctx.strokeStyle = m.color;
  ctx.lineWidth = 1.4 * k;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy, 2.6 * k, 0, Math.PI * 2);
  ctx.fillStyle = m.color;
  ctx.fill();

  ctx.save();
  roundRectPath(ctx, x, y, w, h, 6 * m.lk);
  ctx.clip();
  ctx.fillStyle = CARD_BG;
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = m.color;
  ctx.fillRect(x, y, m.spine, h);

  const tx = x + m.spine + m.lay.px;
  let ty = y + m.lay.py;
  ctx.textBaseline = 'top';

  if (m.l1) {
    let cursor = tx;
    if (m.l1.name) {
      ctx.font = `600 ${12 * m.lk}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
      ctx.fillStyle = NAME_COLOR;
      ctx.fillText(m.l1.name, cursor, ty);
      cursor += ctx.measureText(m.l1.name).width;
    }
    if (m.l1.eps) {
      ctx.font = `${11 * m.lk}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
      ctx.fillStyle = EPS_COLOR;
      ctx.fillText((m.l1.name ? ' ' : '') + m.l1.eps, cursor, ty + (m.l1.name ? 1 * m.lk : 0));
    }
    ty += m.lay.l1h + (m.cols.length ? m.lay.l1Gap : 0);
  }

  if (m.cols.length) {
    let colX = tx;
    for (let i = 0; i < m.cols.length; i++) {
      const c = m.cols[i];
      ctx.font = `${m.lay.keyFont}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
      ctx.fillStyle = KEY_COLOR;
      ctx.fillText(c.key, colX, ty);
      ctx.font = `${11 * m.lk}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.fillStyle = VAL_COLOR;
      ctx.fillText(c.val, colX, ty + m.lay.keyFont + m.lay.rowGap);
      colX += m.lay.colW[i] + m.lay.colGap;
    }
  }
  ctx.restore();

  if (selected) {
    roundRectPath(ctx, x, y, w, h, 6 * m.lk);
    ctx.strokeStyle = NAME_COLOR;
    ctx.lineWidth = 1.5 * k;
    ctx.stroke();
  }
}

function withAlpha(color: string, alpha: number): string {
  // Colours are either `roiColor()`'s `hsl(h, s%, l%)` or a `#rrggbb` the user
  // picked from the swatch.
  const hsl = /^hsl\(([^)]+)\)$/.exec(color);
  if (hsl) return `hsla(${hsl[1]}, ${alpha})`;
  const hex = /^#([0-9a-fA-F]{6})$/.exec(color);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  return color;
}
