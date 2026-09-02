/**
 * ROI models, rasterisation and statistics — the port of `analysis/roi_models.py`
 * and the mask/statistics half of `core/roi_controller.py`.
 *
 * Coordinates are **thermal sensor pixels**, exactly as the desktop stores them
 * in its sidecar JSON (`_create_roi_mask` indexes `thermal_data` with them
 * directly). ROIs may extend outside the sensor; the mask clips, it does not
 * reject.
 */
import { computeTemperaturesAt, type ThermalParameters } from './planck';

export type RoiType = 'RectROI' | 'SpotROI' | 'PolygonROI';

interface RoiCommon {
  id: string;
  name: string;
  /** Per-ROI emissivity; temperatures are recomputed with it. */
  emissivity: number;
  /** Outline colour, `hsl(...)`. */
  color: string;
}

export interface RectRoi extends RoiCommon { type: 'RectROI'; x: number; y: number; width: number; height: number }
export interface SpotRoi extends RoiCommon { type: 'SpotROI'; x: number; y: number; radius: number }
export interface PolygonRoi extends RoiCommon { type: 'PolygonROI'; points: [number, number][] }
export type Roi = RectRoi | SpotRoi | PolygonRoi;

export interface RoiStats {
  min: number;
  max: number;
  mean: number;
  median: number;
  std: number;
  pixels: number;
  /** Sensor pixel holding the coldest / hottest sample in the ROI. */
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export const DEFAULT_ROI_EMISSIVITY = 0.95;

/** `_generate_roi_color`: QColor.fromHsv(hue, 220, 255) stepping 55° per ROI. */
export function roiColor(index: number): string {
  return `hsl(${(index * 55) % 360}, 86%, 57%)`;
}

let counter = 0;
export function nextRoiId(): string {
  return `roi-${Date.now().toString(36)}-${(counter++).toString(36)}`;
}

/** `get_bounds()` → [x1, y1, x2, y2]. */
export function roiBounds(roi: Roi): [number, number, number, number] {
  switch (roi.type) {
    case 'RectROI':
      return [roi.x, roi.y, roi.x + roi.width, roi.y + roi.height];
    case 'SpotROI':
      return [roi.x - roi.radius, roi.y - roi.radius, roi.x + roi.radius, roi.y + roi.radius];
    case 'PolygonROI': {
      if (!roi.points.length) return [0, 0, 0, 0];
      const xs = roi.points.map((p) => p[0]);
      const ys = roi.points.map((p) => p[1]);
      return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    }
  }
}

/** Ray casting, matching `PolygonROI.contains_point` including its edge conventions. */
export function polygonContains(points: [number, number][], x: number, y: number): boolean {
  if (points.length < 3) return false;
  let inside = false;
  let j = points.length - 1;
  for (let i = 0; i < points.length; i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    if (yi !== yj && (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
    j = i;
  }
  return inside;
}

/** Point-in-ROI test for hit detection and for the per-pixel probe. */
export function roiContains(roi: Roi, x: number, y: number): boolean {
  switch (roi.type) {
    case 'RectROI':
      return x >= roi.x && x <= roi.x + roi.width && y >= roi.y && y <= roi.y + roi.height;
    case 'SpotROI':
      return Math.hypot(x - roi.x, y - roi.y) <= roi.radius;
    case 'PolygonROI':
      return polygonContains(roi.points, x, y);
  }
}

/** Python's `int()` truncates toward zero — not `Math.floor`, which differs for negatives. */
const trunc = (v: number) => Math.trunc(v);

/**
 * Flat indices of the sensor pixels a ROI covers, reproducing `_create_roi_mask`
 * bit for bit — including its bounding boxes, its `int()` truncation and the
 * integer pixel coordinates used by the circle and polygon tests.
 */
export function roiMaskIndices(roi: Roi, width: number, height: number): Uint32Array {
  const out: number[] = [];
  const clampX = (v: number) => Math.max(0, Math.min(width, v));
  const clampY = (v: number) => Math.max(0, Math.min(height, v));

  if (roi.type === 'SpotROI') {
    const [bx1, by1, bx2, by2] = roiBounds(roi);
    const x1 = clampX(trunc(bx1)), y1 = clampY(trunc(by1));
    const x2 = clampX(trunc(bx2)), y2 = clampY(trunc(by2));
    const r2 = roi.radius * roi.radius;
    for (let y = y1; y < y2; y++) {
      for (let x = x1; x < x2; x++) {
        const dx = x - roi.x, dy = y - roi.y;
        if (dx * dx + dy * dy <= r2) out.push(y * width + x);
      }
    }
  } else if (roi.type === 'PolygonROI') {
    const [bx1, by1, bx2, by2] = roiBounds(roi);
    const x1 = clampX(trunc(bx1)), y1 = clampY(trunc(by1));
    const x2 = clampX(trunc(bx2)), y2 = clampY(trunc(by2));
    for (let y = y1; y < y2; y++) {
      for (let x = x1; x < x2; x++) {
        if (polygonContains(roi.points, x, y)) out.push(y * width + x);
      }
    }
  } else {
    // Rectangles snap outwards, so a rect never loses a partially covered pixel.
    const x1 = clampX(Math.floor(roi.x)), y1 = clampY(Math.floor(roi.y));
    const x2 = clampX(Math.ceil(roi.x + roi.width)), y2 = clampY(Math.ceil(roi.y + roi.height));
    for (let y = y1; y < y2; y++) {
      for (let x = x1; x < x2; x++) out.push(y * width + x);
    }
  }
  return Uint32Array.from(out);
}

/**
 * Statistics over a ROI, recomputed from raw counts with the ROI's own
 * emissivity (`compute_roi_temperatures`). Returns null when the ROI covers no
 * valid pixel — the caller shows "N/A", as the desktop does.
 */
export function roiStatistics(
  roi: Roi,
  raw: Uint16Array,
  width: number,
  height: number,
  params: ThermalParameters,
): RoiStats | null {
  const indices = roiMaskIndices(roi, width, height);
  if (!indices.length) return null;

  const temps = computeTemperaturesAt(raw, indices, { ...params, Emissivity: roi.emissivity });
  const valid: number[] = [];
  let min = Infinity, max = -Infinity, minFlat = -1, maxFlat = -1, sum = 0;
  for (let i = 0; i < temps.length; i++) {
    const v = temps[i];
    if (Number.isNaN(v)) continue;
    valid.push(v);
    if (v < min) { min = v; minFlat = indices[i]; }
    if (v > max) { max = v; maxFlat = indices[i]; }
    sum += v;
  }
  if (!valid.length) return null;
  const mean = sum / valid.length;

  let sq = 0;
  for (const v of valid) sq += (v - mean) * (v - mean);
  const std = Math.sqrt(sq / valid.length); // numpy's population std

  const sorted = Float64Array.from(valid).sort();
  const mid = sorted.length >> 1;
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;

  return {
    min, max, mean, median, std, pixels: valid.length,
    minX: minFlat % width, minY: Math.trunc(minFlat / width),
    maxX: maxFlat % width, maxY: Math.trunc(maxFlat / width),
  };
}

/** Moves a ROI by a delta in sensor pixels. */
export function translateRoi(roi: Roi, dx: number, dy: number): void {
  if (roi.type === 'PolygonROI') {
    roi.points = roi.points.map(([x, y]) => [x + dx, y + dy] as [number, number]);
  } else {
    roi.x += dx;
    roi.y += dy;
  }
}
