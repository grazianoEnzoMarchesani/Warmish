/**
 * The aggregate files that sit at the root of an export: the single ROI table
 * (`aree.csv`), the run description (`manifest.json`) and the capture points
 * (`punti_scatto.geojson`).
 *
 * `aree.csv` targets **Excel italiano**: `;` separator, `,` decimal, a UTF-8 BOM
 * and CRLF line endings. One row per ROI; images with no ROI do not appear
 * (they are still listed in the manifest).
 */
import type { GpsFix } from './exif';
import type { Roi, RoiStats } from './roi';
import type { ThermalParameters } from './planck';

export interface CaptureContext {
  /** Original file name, e.g. `IR_0001.jpg`. */
  image: string;
  /** Sub-folder inside the export holding this image's rasters. */
  folder: string;
  datetime: string | null;
  gps: GpsFix | null;
  camera: string | null;
  width: number;
  height: number;
}

export interface AreaRow {
  ctx: CaptureContext;
  roi: Roi;
  stats: RoiStats | null;
  /** Scene parameters actually used for this ROI (emissivity is per-ROI). */
  params: ThermalParameters;
  objectDistance: number;
}

const AREE_HEADER = [
  'immagine', 'data_ora', 'latitudine', 'longitudine', 'quota_m', 'direzione_deg',
  'roi', 'forma', 'geometria', 'centro_x', 'centro_y', 'area_px', 'emissivita',
  'temp_riflessa_c', 'temp_atmosferica_c', 'umidita_pct', 'distanza_m', 'trasmittanza_atm',
  'min_c', 'max_c', 'media_c', 'mediana_c', 'dev_std_c',
  'pos_min_x', 'pos_min_y', 'pos_max_x', 'pos_max_y',
  'camera', 'larghezza_px', 'altezza_px',
];

const FORMA: Record<Roi['type'], string> = {
  RectROI: 'Rettangolo', SpotROI: 'Punto', PolygonROI: 'Poligono',
};

/** Decimal with a comma, for Excel italiano. Empty string for missing values. */
function dec(v: number | null | undefined, digits = 4): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '' : v.toFixed(digits).replace('.', ',');
}

/** A cell is quoted only when it holds the separator, a quote or a newline. */
function cell(v: string): string {
  return /[;"\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function geometry(roi: Roi): string {
  const r = Math.round;
  if (roi.type === 'RectROI') return `RETT x=${r(roi.x)} y=${r(roi.y)} l=${r(roi.width)} h=${r(roi.height)}`;
  if (roi.type === 'SpotROI') return `PUNTO x=${r(roi.x)} y=${r(roi.y)} r=${r(roi.radius)}`;
  return `POLIGONO ${roi.points.map(([x, y]) => `${r(x)} ${r(y)}`).join(' ')}`;
}

function roiCentre(roi: Roi): [number, number] {
  if (roi.type === 'RectROI') return [roi.x + roi.width / 2, roi.y + roi.height / 2];
  if (roi.type === 'SpotROI') return [roi.x, roi.y];
  const n = roi.points.length || 1;
  const sx = roi.points.reduce((a, p) => a + p[0], 0);
  const sy = roi.points.reduce((a, p) => a + p[1], 0);
  return [sx / n, sy / n];
}

export function buildAreeCsv(rows: AreaRow[]): string {
  const lines = [AREE_HEADER.join(';')];
  for (const { ctx, roi, stats, params, objectDistance } of rows) {
    const [cx, cy] = roiCentre(roi);
    lines.push([
      ctx.image,
      ctx.datetime ?? '',
      dec(ctx.gps?.lat ?? null, 6),
      dec(ctx.gps?.lon ?? null, 6),
      dec(ctx.gps?.altitude ?? null, 1),
      dec(ctx.gps?.direction ?? null, 1),
      roi.name,
      FORMA[roi.type],
      geometry(roi),
      String(Math.round(cx)),
      String(Math.round(cy)),
      String(stats?.pixels ?? 0),
      dec(roi.emissivity, 3),
      dec(params.ReflectedApparentTemperature, 2),
      dec(params.AtmosphericTemperature, 2),
      dec(params.RelativeHumidity, 1),
      dec(objectDistance, 2),
      dec(params.AtmosphericTransmission, 3),
      dec(stats?.min), dec(stats?.max), dec(stats?.mean), dec(stats?.median), dec(stats?.std),
      stats ? String(stats.minX) : '', stats ? String(stats.minY) : '',
      stats ? String(stats.maxX) : '', stats ? String(stats.maxY) : '',
      ctx.camera ?? '',
      String(ctx.width), String(ctx.height),
    ].map(cell).join(';'));
  }
  return '﻿' + lines.join('\r\n') + '\r\n';
}

// --- manifest.json ---------------------------------------------------------

export interface ManifestImage {
  file: string;
  folder: string;
  dimensions: [number, number];
  camera: string | null;
  datetime: string | null;
  gps: { lat: number; lon: number; alt_m: number | null; direction_deg: number | null } | null;
  parameters: Record<string, number>;
  roi_count: number;
  outputs: string[];
}

export interface ManifestInput {
  warmishVersion: string;
  exportedAt: string;
  render: Record<string, unknown>;
  /** Global parameter override applied to every image, or null when each keeps its own. */
  parameters: Record<string, number> | null;
  images: ManifestImage[];
}

export function buildManifest(m: ManifestInput): string {
  return JSON.stringify({
    warmish_version: m.warmishVersion,
    exported_at: m.exportedAt,
    image_count: m.images.length,
    csv_format: { delimiter: ';', decimal: ',', encoding: 'utf-8-bom', newline: 'crlf' },
    render: m.render,
    parameters: m.parameters,
    images: m.images,
  }, null, 2);
}

// --- punti_scatto.geojson -------------------------------------------------

export interface GeoPoint {
  image: string;
  folder: string;
  datetime: string | null;
  gps: GpsFix;
}

export function buildGeojson(points: GeoPoint[]): string {
  return JSON.stringify({
    type: 'FeatureCollection',
    features: points.map((p) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: p.gps.altitude !== null
          ? [p.gps.lon, p.gps.lat, p.gps.altitude]
          : [p.gps.lon, p.gps.lat],
      },
      properties: {
        immagine: p.image,
        cartella: p.folder,
        data_ora: p.datetime,
        direzione_deg: p.gps.direction,
      },
    })),
  }, null, 2);
}
