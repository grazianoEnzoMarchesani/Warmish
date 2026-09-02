/**
 * One image, from bytes to exportable files — shared by the single-image export
 * and by the batch worker, so the two can never drift.
 *
 * Per-image output set (see OUTPUTS.md):
 *   termica.png            native 640×480, no decoration
 *   termica_annotata.png   4×, bottom legend, no ROI
 *   termica_aree.png       4×, bottom legend + ROI + labels — only if ROIs
 *   sovrapposta.png        ≤2560px, legend + ROI + labels — only if overlay on
 *   visibile.jpg           original resolution, parent EXIF grafted in
 * plus the session `.json` and the rows/manifest/geojson fragments the caller
 * assembles into the aggregate files.
 */
import { parseThermalImage, type FlirMetadata, type ThermalFile } from './flir';
import { parseCapture, parseGps, extractExifApp1, injectExifApp1 } from './exif';
import { colorize, getLut } from './colormap';
import {
  canvasToJpeg, canvasToPng, composite, context2d, createCanvas, drawLegendH, imageDataToCanvas,
  type AnyCanvas, type BlendMode, type CompositeResult, type OverlayAlignment,
} from './render';
import { computeTemperatures, parametersFromMetadata, percentileRange, temperatureRange, type ThermalParameters } from './planck';
import { applyVisibleFilter, isIdentityFilter, type VisibleFilter } from './imageFilter';
import { roiStatistics, type Roi, type RoiStats } from './roi';
import { drawRois, type RoiLabelSettings } from './roiRender';
import { buildSession } from './session';
import type { AreaRow, GeoPoint, ManifestImage } from './report';

/** Long edge of every decorated PNG. 640×480 thermal → exactly 4×. */
export const DECORATED_LONG_EDGE = 2560;

/** The parameters a user can override; Planck constants always come from the file. */
export type UserParameters = Pick<
  ThermalParameters,
  'Emissivity' | 'ReflectedApparentTemperature' | 'AtmosphericTemperature' | 'AtmosphericTransmission' | 'RelativeHumidity'
>;

export interface RenderSettings {
  palette: string;
  inverted: boolean;
  autoRange: boolean;
  /** Auto-range mode: 0 keeps the true min/max, >0 clips to that central
   *  percentile of the pixels (linear stretch). Ignored when `autoRange` is off. */
  stretchPct: number;
  manualMin: number;
  manualMax: number;
  showVisible: boolean;
  blend: BlendMode;
  opacity: number;
  alignment: OverlayAlignment;
  /** Filter applied to the embedded visible photo before compositing. */
  visibleFilter: VisibleFilter;
  labels: RoiLabelSettings;
  rois: Roi[];
  /** null → each image keeps its own calibration, which is the safe default. */
  parameters: UserParameters | null;
}

export function resolveParameters(metadata: FlirMetadata, override: UserParameters | null): ThermalParameters {
  const own = parametersFromMetadata(metadata);
  return override ? { ...own, ...override } : own;
}

export interface ProcessedFile {
  /** Name inside the image folder, no path. */
  name: string;
  blob: Blob;
}

export interface ImageResult {
  folder: string;
  outputs: ProcessedFile[];
  sessionJson: string;
  rows: AreaRow[];
  manifestImage: ManifestImage;
  geo: GeoPoint | null;
}

interface Decorations {
  rois?: Roi[];
  stats?: Map<string, RoiStats | null>;
  labels?: RoiLabelSettings;
  legend?: { palette: string; inverted: boolean; min: number; max: number; histogram?: number[] };
}

/** Temperature distribution across `[min, max]`, coldest bin first — the flat
 * echo of the in-canvas range scale, burned into the export legend. */
const LEGEND_HIST_BINS = 48;
function legendHistogram(temps: Float64Array, min: number, max: number): number[] {
  const span = max - min || 1;
  const bins = new Array<number>(LEGEND_HIST_BINS).fill(0);
  for (let i = 0; i < temps.length; i++) {
    const v = temps[i];
    if (Number.isNaN(v) || v < min || v > max) continue;
    let b = Math.floor(((v - min) / span) * LEGEND_HIST_BINS);
    if (b < 0) b = 0; else if (b >= LEGEND_HIST_BINS) b = LEGEND_HIST_BINS - 1;
    bins[b]++;
  }
  return bins;
}

/**
 * Copies a composited view onto a fixed-size export canvas, scaling it up (or,
 * for a large visible frame, down) to `DECORATED_LONG_EDGE`, then burning in the
 * ROI layer and a horizontal colour bar underneath. Deterministic: nothing here
 * depends on the interactive viewer's zoom or window size.
 */
function decorate(view: CompositeResult, d: Decorations): AnyCanvas {
  const scale = clamp(DECORATED_LONG_EDGE / Math.max(view.width, view.height), 1, 4);
  const imgW = Math.round(view.width * scale);
  const imgH = Math.round(view.height * scale);
  const uiK = Math.max(1, imgW / 900);
  const band = d.legend ? Math.round((d.legend.histogram?.length ? 74 : 46) * uiK) : 0;

  const out = createCanvas(imgW, imgH + band);
  const ctx = context2d(out);
  ctx.fillStyle = '#101216';
  ctx.fillRect(0, 0, imgW, imgH + band);
  // Thermal wants crisp pixels when enlarged; a visible photo does not.
  ctx.imageSmoothingEnabled = view.scale !== 1 || view.offsetX !== 0 || view.offsetY !== 0;
  ctx.drawImage(view.canvas, 0, 0, imgW, imgH);
  ctx.imageSmoothingEnabled = true;

  if (d.rois?.length) {
    drawRois(ctx, {
      rois: d.rois,
      stats: d.stats ?? new Map(),
      labels: d.labels!,
      transform: { scale: view.scale * scale, offsetX: view.offsetX * scale, offsetY: view.offsetY * scale },
      uiScale: uiK,
      bounds: { width: imgW, height: imgH },
    });
  }
  if (d.legend) {
    const m = Math.round(20 * uiK);
    drawLegendH(ctx, getLut(d.legend.palette), d.legend.inverted, d.legend.min, d.legend.max,
      m, imgH + Math.round(4 * uiK), imgW - 2 * m, band - Math.round(8 * uiK), uiK, d.legend.histogram);
  }
  return out;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/**
 * One decorated frame of a single image — the same pixels `processImage` would
 * put in `sovrapposta.png` (overlay on) / `termica_aree.png` (ROIs) /
 * `termica_annotata.png`, as a JPEG for on-screen use. Used by the map tour so
 * the panel shows exactly what an export would produce. Not an export path — it
 * never touches EXIF, sessions or the zip.
 */
export async function renderHeroImage(bytes: Uint8Array, s: RenderSettings): Promise<Blob> {
  const parsed: ThermalFile = parseThermalImage(bytes);
  const params = resolveParameters(parsed.metadata, s.parameters);
  const temps = computeTemperatures(parsed.raw, params);
  const auto = s.stretchPct > 0 ? percentileRange(temps, s.stretchPct) : temperatureRange(temps);
  const range = s.autoRange ? auto : { min: s.manualMin, max: s.manualMax };

  const thermal = imageDataToCanvas(
    colorize(temps, { palette: s.palette, inverted: s.inverted, min: range.min, max: range.max }),
    parsed.width, parsed.height,
  );

  const stats = new Map<string, RoiStats | null>();
  for (const roi of s.rois) {
    stats.set(roi.id, roiStatistics(roi, parsed.raw, parsed.width, parsed.height, params));
  }
  const legend = {
    palette: s.palette, inverted: s.inverted, min: range.min, max: range.max,
    histogram: legendHistogram(temps, range.min, range.max),
  };

  let view: CompositeResult;
  if (s.showVisible && parsed.visible) {
    const bitmap = await createImageBitmap(new Blob([parsed.visible as BlobPart], { type: 'image/jpeg' }));
    const visible = isIdentityFilter(s.visibleFilter) ? bitmap : applyVisibleFilter(bitmap, s.visibleFilter);
    view = composite({
      thermal, width: parsed.width, height: parsed.height, visible,
      blend: s.blend, opacity: s.opacity, alignment: s.alignment,
    });
    bitmap.close();
  } else {
    view = composite({ thermal, width: parsed.width, height: parsed.height, visible: null, blend: s.blend, opacity: 1 });
  }

  return canvasToJpeg(decorate(view, { rois: s.rois, stats, labels: s.labels, legend }), 0.85);
}

/** Everything a single image contributes to an export. */
export async function processImage(bytes: Uint8Array, folder: string, s: RenderSettings): Promise<ImageResult> {
  const parsed: ThermalFile = parseThermalImage(bytes);
  const params = resolveParameters(parsed.metadata, s.parameters);
  const temps = computeTemperatures(parsed.raw, params);
  const auto = s.stretchPct > 0 ? percentileRange(temps, s.stretchPct) : temperatureRange(temps);
  const range = s.autoRange ? auto : { min: s.manualMin, max: s.manualMax };
  const capture = parseCapture(bytes);
  const gps = parseGps(bytes);

  const thermal = imageDataToCanvas(
    colorize(temps, { palette: s.palette, inverted: s.inverted, min: range.min, max: range.max }),
    parsed.width, parsed.height,
  );

  const stats = new Map<string, RoiStats | null>();
  for (const roi of s.rois) {
    stats.set(roi.id, roiStatistics(roi, parsed.raw, parsed.width, parsed.height, params));
  }

  const legend = {
    palette: s.palette, inverted: s.inverted, min: range.min, max: range.max,
    histogram: legendHistogram(temps, range.min, range.max),
  };
  const outputs: ProcessedFile[] = [];

  const plain = composite({ thermal, width: parsed.width, height: parsed.height, visible: null, blend: s.blend, opacity: 1 });

  outputs.push({ name: 'termica.png', blob: await canvasToPng(plain.canvas) });
  outputs.push({ name: 'termica_annotata.png', blob: await canvasToPng(decorate(plain, { legend })) });
  if (s.rois.length) {
    outputs.push({
      name: 'termica_aree.png',
      blob: await canvasToPng(decorate(plain, { rois: s.rois, stats, labels: s.labels, legend })),
    });
  }

  const hasVisible = parsed.visible !== null;
  if (hasVisible) {
    const grafted = injectExifApp1(parsed.visible as Uint8Array, extractExifApp1(bytes));
    outputs.push({ name: 'visibile.jpg', blob: new Blob([grafted as BlobPart], { type: 'image/jpeg' }) });

    if (s.showVisible) {
      const bitmap = await createImageBitmap(new Blob([parsed.visible as BlobPart], { type: 'image/jpeg' }));
      const visible = isIdentityFilter(s.visibleFilter) ? bitmap : applyVisibleFilter(bitmap, s.visibleFilter);
      const over = composite({
        thermal, width: parsed.width, height: parsed.height, visible,
        blend: s.blend, opacity: s.opacity, alignment: s.alignment,
      });
      outputs.push({
        name: 'sovrapposta.png',
        blob: await canvasToPng(decorate(over, { rois: s.rois, stats, labels: s.labels, legend })),
      });
      bitmap.close();
    }
  }

  const sessionJson = JSON.stringify(buildSession({
    parameters: params, objectDistance: parsed.metadata.ObjectDistance,
    palette: s.palette, inverted: s.inverted, autoRange: s.autoRange, stretchPct: s.stretchPct,
    manualMin: s.manualMin, manualMax: s.manualMax, showVisible: s.showVisible,
    blend: s.blend, opacity: s.opacity, alignment: s.alignment, visibleFilter: s.visibleFilter,
    labels: s.labels, rois: s.rois,
  }), null, 2);

  const ctx: AreaRow['ctx'] = {
    image: `${folder}.jpg`, folder, datetime: capture.datetime, gps,
    camera: capture.camera, width: parsed.width, height: parsed.height,
  };

  const paramRecord = {
    Emissivity: params.Emissivity,
    ReflectedApparentTemperature: params.ReflectedApparentTemperature,
    AtmosphericTemperature: params.AtmosphericTemperature,
    AtmosphericTransmission: params.AtmosphericTransmission,
    RelativeHumidity: params.RelativeHumidity,
    ObjectDistance: parsed.metadata.ObjectDistance,
  };

  return {
    folder,
    outputs,
    sessionJson,
    rows: s.rois.map((roi) => ({ ctx, roi, stats: stats.get(roi.id) ?? null, params, objectDistance: parsed.metadata.ObjectDistance })),
    manifestImage: {
      file: ctx.image, folder,
      dimensions: [parsed.width, parsed.height],
      camera: capture.camera, datetime: capture.datetime,
      gps: gps ? { lat: gps.lat, lon: gps.lon, alt_m: gps.altitude, direction_deg: gps.direction } : null,
      parameters: paramRecord,
      roi_count: s.rois.length,
      outputs: outputs.map((o) => o.name),
    },
    geo: gps ? { image: ctx.image, folder, datetime: capture.datetime, gps } : null,
  };
}
