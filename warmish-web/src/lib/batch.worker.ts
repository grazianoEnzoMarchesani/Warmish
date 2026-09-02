/**
 * Export assembly off the main thread.
 *
 * Produces one zip with the structure described in OUTPUTS.md: a folder per
 * image, an `originali/` kit (session `.json` + optionally the source JPEG), and
 * the aggregate `aree.csv` / `manifest.json` / `punti_scatto.geojson` at the
 * root. The single-image export and the batch both come through here, so the
 * two output sets cannot drift.
 */
import { zipSync, type Zippable } from 'fflate';

import { processImage, DECORATED_LONG_EDGE, type RenderSettings } from '../core/pipeline';
import { buildAreeCsv, buildManifest, buildGeojson, type AreaRow, type GeoPoint, type ManifestImage } from '../core/report';

export interface BatchRequest {
  files: File[];
  settings: RenderSettings;
  /** Per-image overrides, parallel to `files`; a null slot keeps `settings`. */
  perFile?: (Partial<RenderSettings> | null)[];
  includeOriginals: boolean;
  /** `YYYY-MM-DD`, names the zip's root folder. */
  exportDate: string;
  warmishVersion: string;
}

export type BatchMessage =
  | { type: 'progress'; done: number; total: number; name: string }
  | { type: 'done'; zip: ArrayBuffer; processed: number; failures: { name: string; message: string }[] }
  | { type: 'fatal'; message: string };

const scope = self as unknown as { postMessage(m: BatchMessage, transfer?: Transferable[]): void };
const post = (m: BatchMessage, transfer: Transferable[] = []) => scope.postMessage(m, transfer);

self.onmessage = async (ev: MessageEvent<BatchRequest>) => {
  const { files, settings, perFile, includeOriginals, exportDate, warmishVersion } = ev.data;
  const root = `warmish_export_${exportDate}`;
  const entries: Zippable = {};
  const failures: { name: string; message: string }[] = [];
  const rows: AreaRow[] = [];
  const manifestImages: ManifestImage[] = [];
  const geoPoints: GeoPoint[] = [];
  const usedFolders = new Set<string>();
  let processed = 0;

  const uniqueFolder = (fileName: string): string => {
    const base = fileName.replace(/\.[^.]+$/, '') || 'immagine';
    let f = base;
    for (let i = 2; usedFolders.has(f); i++) f = `${base}_${i}`;
    usedFolders.add(f);
    return f;
  };

  try {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      post({ type: 'progress', done: i, total: files.length, name: file.name });
      const s = perFile?.[i] ? { ...settings, ...perFile[i] } : settings;
      try {
        const bytes = new Uint8Array(await file.arrayBuffer());
        const folder = uniqueFolder(file.name);
        const result = await processImage(bytes, folder, s);

        for (const out of result.outputs) {
          entries[`${root}/${folder}/${out.name}`] = new Uint8Array(await out.blob.arrayBuffer());
        }
        entries[`${root}/originali/${folder}.json`] = new TextEncoder().encode(result.sessionJson);
        if (includeOriginals) entries[`${root}/originali/${folder}.jpg`] = bytes;

        rows.push(...result.rows);
        manifestImages.push(result.manifestImage);
        if (result.geo) geoPoints.push(result.geo);
        processed++;
      } catch (e) {
        failures.push({ name: file.name, message: e instanceof Error ? e.message : String(e) });
      }
    }
    post({ type: 'progress', done: files.length, total: files.length, name: '' });

    entries[`${root}/aree.csv`] = new TextEncoder().encode(buildAreeCsv(rows));
    entries[`${root}/manifest.json`] = new TextEncoder().encode(buildManifest({
      warmishVersion,
      exportedAt: new Date().toISOString(),
      render: {
        palette: settings.palette,
        inverted: settings.inverted,
        range: settings.autoRange
          ? (settings.stretchPct > 0
              ? { mode: 'stretch', percentile: settings.stretchPct }
              : { mode: 'auto' })
          : { mode: 'manual', min: settings.manualMin, max: settings.manualMax },
        legend: true,
        decorated_long_edge: DECORATED_LONG_EDGE,
        overlay: settings.showVisible
          ? {
              blend: settings.blend, opacity: settings.opacity,
              alignment: settings.alignment, visible_filter: settings.visibleFilter,
            }
          : null,
        labels: settings.labels,
      },
      parameters: settings.parameters
        ? { ...settings.parameters } as Record<string, number>
        : null,
      images: manifestImages,
    }));
    if (geoPoints.length) {
      entries[`${root}/punti_scatto.geojson`] = new TextEncoder().encode(buildGeojson(geoPoints));
    }
    if (!includeOriginals) {
      entries[`${root}/originali/NOTA.txt`] = new TextEncoder().encode(
        'Le sessioni .json qui accanto vanno riaperte insieme alle immagini FLIR di partenza,\n'
        + 'che non sono state incluse in questo export.\n',
      );
    }
    if (failures.length) {
      entries[`${root}/errori.txt`] = new TextEncoder().encode(
        failures.map((f) => `${f.name}: ${f.message}`).join('\n') + '\n',
      );
    }

    // PNG and JPEG are already compressed; deflating them again only costs time.
    const zip = zipSync(entries, { level: 0 });
    post({ type: 'done', zip: zip.buffer as ArrayBuffer, processed, failures }, [zip.buffer as ArrayBuffer]);
  } catch (e) {
    post({ type: 'fatal', message: e instanceof Error ? e.message : String(e) });
  }
};
