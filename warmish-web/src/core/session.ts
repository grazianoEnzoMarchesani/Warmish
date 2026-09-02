/**
 * Session sidecar I/O — the browser's replacement for `core/settings_manager.py`.
 *
 * The schema is the desktop's, unchanged, so a `<image>.json` written by either
 * app opens in the other. What cannot be reproduced is the desktop's silent
 * auto-save next to the image: a web page has no such write access, so saving is
 * an explicit download and resuming means opening the JSON alongside the image.
 */
import {
  DEFAULT_LABEL_SETTINGS, LABEL_SCALE_MAX, LABEL_SCALE_MIN, type RoiLabelSettings,
} from './roiRender';
import { DEFAULT_ROI_EMISSIVITY, nextRoiId, roiColor, type Roi } from './roi';
import { BLEND_NAMES, DEFAULT_ALIGNMENT, type BlendMode, type OverlayAlignment } from './render';
import { FILTER_NAMES, type FilterName, type VisibleFilter } from './imageFilter';
import { PALETTE_NAMES } from './colormap';
import type { ThermalParameters } from './planck';

export interface SessionState {
  parameters: ThermalParameters;
  objectDistance: number;
  palette: string;
  inverted: boolean;
  autoRange: boolean;
  /** Auto-range stretch: 0 = true min/max, >0 = central percentile kept. Web-only. */
  stretchPct: number;
  manualMin: number;
  manualMax: number;
  showVisible: boolean;
  blend: BlendMode;
  /** Thermal layer opacity, 0..1. */
  opacity: number;
  alignment: OverlayAlignment;
  /** Filter on the visible photo. Web-only; desktop ignores the unknown key. */
  visibleFilter?: VisibleFilter;
  labels: RoiLabelSettings;
  rois: Roi[];
}

/**
 * Desktop sidecars carry RelativeHumidity as a fraction, because the desktop
 * reads it through ExifTool's numeric mode and never converts (see HANDOFF §4).
 * Its own default is `50.0`, so the file format is ambiguous; anything at or
 * below this threshold is read as a fraction. 1.5 % humidity is not a
 * measurement any camera reports, so the test is safe in practice.
 */
const FRACTION_THRESHOLD = 1.5;

export function humidityToPercent(value: number): number {
  return value <= FRACTION_THRESHOLD ? value * 100 : value;
}

export function buildSession(s: SessionState): Record<string, unknown> {
  return {
    version: '1.0',
    thermal_parameters: {
      Emissivity: s.parameters.Emissivity,
      AtmosphericTemperature: s.parameters.AtmosphericTemperature,
      AtmosphericTransmission: s.parameters.AtmosphericTransmission,
      // Written as percent — self-consistent with this app and with the
      // desktop's own defaults, and read back correctly by the rule above.
      RelativeHumidity: s.parameters.RelativeHumidity,
      ObjectDistance: s.objectDistance,
      ReflectedApparentTemperature: s.parameters.ReflectedApparentTemperature,
    },
    palette: s.palette,
    palette_inverted: s.inverted,
    temp_range_settings: {
      mode: s.autoRange ? 'autorange' : 'manual',
      manual_min: s.manualMin,
      manual_max: s.manualMax,
      // Web-only extension; the desktop ignores the unknown key and falls back
      // to a plain autorange.
      stretch_pct: s.stretchPct || undefined,
    },
    overlay_settings: {
      scale: s.alignment.scale,
      offset_x: s.alignment.offsetX,
      offset_y: s.alignment.offsetY,
      opacity: Math.round(s.opacity * 100),
      blend_mode: s.blend,
    },
    visible_filter: s.visibleFilter && s.visibleFilter.name !== 'none'
      ? { name: s.visibleFilter.name, strength: s.visibleFilter.strength }
      : undefined,
    roi_label_settings: { ...s.labels },
    rois: s.rois.map(serialiseRoi),
  };
}

function serialiseRoi(roi: Roi): Record<string, unknown> {
  const base = { type: roi.type, name: roi.name, emissivity: roi.emissivity, color: roi.color };
  if (roi.type === 'RectROI') return { ...base, x: roi.x, y: roi.y, width: roi.width, height: roi.height };
  if (roi.type === 'SpotROI') return { ...base, x: roi.x, y: roi.y, radius: roi.radius };
  return { ...base, points: roi.points.map(([x, y]) => [x, y]) };
}

/** Everything a session file may override; absent keys stay untouched. */
export type SessionPatch = Partial<Omit<SessionState, 'parameters'>> & {
  parameters?: Partial<ThermalParameters>;
};

/**
 * Reads a sidecar, keeping only values that are actually usable. Unknown
 * palettes and blend modes are dropped rather than applied, since a mismatched
 * name would otherwise blank the render.
 */
export function parseSession(json: unknown): SessionPatch {
  if (!json || typeof json !== 'object') throw new Error('Il file di sessione non è un oggetto JSON');
  const d = json as Record<string, any>;
  const patch: SessionPatch = {};

  if (isObject(d.thermal_parameters)) {
    const t = d.thermal_parameters;
    const p: Partial<ThermalParameters> = {};
    if (isNum(t.Emissivity)) p.Emissivity = t.Emissivity;
    if (isNum(t.AtmosphericTemperature)) p.AtmosphericTemperature = t.AtmosphericTemperature;
    if (isNum(t.AtmosphericTransmission)) p.AtmosphericTransmission = t.AtmosphericTransmission;
    if (isNum(t.RelativeHumidity)) p.RelativeHumidity = humidityToPercent(t.RelativeHumidity);
    if (isNum(t.ReflectedApparentTemperature)) p.ReflectedApparentTemperature = t.ReflectedApparentTemperature;
    if (Object.keys(p).length) patch.parameters = p;
    if (isNum(t.ObjectDistance)) patch.objectDistance = t.ObjectDistance;
  }

  if (typeof d.palette === 'string' && (PALETTE_NAMES as string[]).includes(d.palette)) patch.palette = d.palette;
  if (typeof d.palette_inverted === 'boolean') patch.inverted = d.palette_inverted;

  if (isObject(d.temp_range_settings)) {
    const r = d.temp_range_settings;
    if (typeof r.mode === 'string') patch.autoRange = r.mode !== 'manual';
    if (isNum(r.manual_min)) patch.manualMin = r.manual_min;
    if (isNum(r.manual_max)) patch.manualMax = r.manual_max;
    if (isNum(r.stretch_pct)) patch.stretchPct = Math.min(99.9, Math.max(0, r.stretch_pct));
  }

  if (isObject(d.overlay_settings)) {
    const o = d.overlay_settings;
    const alignment: OverlayAlignment = { ...DEFAULT_ALIGNMENT };
    if (isNum(o.scale)) alignment.scale = Math.min(5, Math.max(0.1, o.scale));
    if (isNum(o.offset_x)) alignment.offsetX = o.offset_x;
    if (isNum(o.offset_y)) alignment.offsetY = o.offset_y;
    patch.alignment = alignment;
    if (isNum(o.opacity)) patch.opacity = Math.min(1, Math.max(0, o.opacity / 100));
    if (typeof o.blend_mode === 'string' && (BLEND_NAMES as string[]).includes(o.blend_mode)) {
      patch.blend = o.blend_mode as BlendMode;
    }
  }

  if (isObject(d.visible_filter)) {
    const vf = d.visible_filter;
    if (typeof vf.name === 'string' && (FILTER_NAMES as string[]).includes(vf.name)) {
      patch.visibleFilter = {
        name: vf.name as FilterName,
        strength: isNum(vf.strength) ? Math.min(100, Math.max(0, vf.strength)) : 50,
      };
    }
  }

  if (isObject(d.roi_label_settings)) {
    const labels = { ...DEFAULT_LABEL_SETTINGS };
    const boolKeys = ['name', 'emissivity', 'min', 'max', 'avg', 'median'] as const;
    for (const key of boolKeys) {
      if (typeof d.roi_label_settings[key] === 'boolean') labels[key] = d.roi_label_settings[key];
    }
    if (isNum(d.roi_label_settings.scale)) {
      labels.scale = Math.min(LABEL_SCALE_MAX, Math.max(LABEL_SCALE_MIN, d.roi_label_settings.scale));
    }
    patch.labels = labels;
  }

  if (Array.isArray(d.rois)) patch.rois = d.rois.map(parseRoi).filter((r): r is Roi => r !== null);

  return patch;
}

function parseRoi(data: any, index: number): Roi | null {
  if (!isObject(data)) return null;
  const emissivity = isNum(data.emissivity) ? data.emissivity : DEFAULT_ROI_EMISSIVITY;
  // `color` is a Warmish extension to the sidecar; older files without it fall
  // back to the index-derived colour, matching the desktop.
  const color = typeof data.color === 'string' && data.color ? data.color : roiColor(index);
  const id = nextRoiId();

  if (data.type === 'SpotROI' && isNum(data.x) && isNum(data.y)) {
    return { id, type: 'SpotROI', name: name(data, `Spot_${index + 1}`), emissivity, color,
      x: data.x, y: data.y, radius: isNum(data.radius) ? data.radius : 5 };
  }
  if (data.type === 'PolygonROI' && Array.isArray(data.points)) {
    const points = data.points
      .filter((p: any) => Array.isArray(p) && isNum(p[0]) && isNum(p[1]))
      .map((p: any) => [p[0], p[1]] as [number, number]);
    if (points.length < 3) return null;
    return { id, type: 'PolygonROI', name: name(data, `Polygon_${index + 1}`), emissivity, color, points };
  }
  if (data.type === 'RectROI' && isNum(data.x) && isNum(data.y)) {
    return { id, type: 'RectROI', name: name(data, `Rectangle_${index + 1}`), emissivity, color,
      x: data.x, y: data.y,
      width: isNum(data.width) ? data.width : 50,
      height: isNum(data.height) ? data.height : 50 };
  }
  return null;
}

const name = (data: any, fallback: string) => (typeof data.name === 'string' && data.name ? data.name : fallback);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isObject = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v);

/** CSV of per-ROI statistics, the counterpart of the desktop's stats export. */
export function roiStatsCsv(
  rois: Roi[],
  stats: Map<string, { min: number; max: number; mean: number; median: number; std: number; pixels: number } | null>,
): string {
  const rows = [['name', 'type', 'emissivity', 'pixels', 'min_c', 'max_c', 'mean_c', 'median_c', 'std_c']];
  for (const roi of rois) {
    const s = stats.get(roi.id) ?? null;
    const num = (v: number | undefined) => (v === undefined ? '' : v.toFixed(4));
    rows.push([
      roi.name, roi.type, roi.emissivity.toFixed(3), String(s?.pixels ?? 0),
      num(s?.min), num(s?.max), num(s?.mean), num(s?.median), num(s?.std),
    ]);
  }
  return rows.map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
}

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
