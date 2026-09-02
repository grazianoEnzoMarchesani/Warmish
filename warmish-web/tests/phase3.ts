/**
 * Phase-3 gate: ROI masks and statistics must match the desktop's ROIController,
 * and a session sidecar must survive a round trip through both apps' schema.
 *
 *   npx tsx tests/phase3.ts
 *
 * References come from tests/python_roi_reference.py driving the real
 * core/roi_controller.py, so this compares against the shipping implementation.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { parseThermalImage } from '../src/core/flir';
import { parametersFromMetadata } from '../src/core/planck';
import { roiMaskIndices, roiStatistics, type Roi } from '../src/core/roi';
import { buildSession, parseSession } from '../src/core/session';
import { buildAreeCsv, type AreaRow } from '../src/core/report';
import { DEFAULT_LABEL_SETTINGS } from '../src/core/roiRender';
import { DEFAULT_ALIGNMENT } from '../src/core/render';

const REPO = resolve(import.meta.dirname, '../..');
const SAMPLES = join(REPO, 'exemple img');
const REFS = join(import.meta.dirname, 'reference');
const PYTHON = existsSync(join(REPO, 'venv/bin/python3')) ? join(REPO, 'venv/bin/python3') : 'python3';

const TOL = 1e-6; // °C

let failures = 0;
function check(label: string, ok: boolean, detail = ''): void {
  if (ok) console.log(`  ok   ${label}`);
  else { failures++; console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`); }
}

/**
 * Deliberately awkward geometry: a rectangle straddling the left edge, a spot
 * clipped by the top edge, a polygon partly below the sensor and a fully
 * outside rectangle — the cases where mask clipping and Python's `int()`
 * truncation are easy to get wrong.
 */
const ROI_FIXTURE = [
  { type: 'RectROI', name: 'R_inside', emissivity: 0.95, x: 40.4, y: 30.6, width: 60.2, height: 45.8 },
  { type: 'RectROI', name: 'R_clipped', emissivity: 0.62, x: -22.0, y: 131.0, width: 84.45747800586511, height: 71.08504398826979 },
  { type: 'RectROI', name: 'R_outside', emissivity: 0.95, x: 900.0, y: 900.0, width: 20.0, height: 20.0 },
  { type: 'SpotROI', name: 'S_centre', emissivity: 0.98, x: 162.4489223831188, y: 98.76327933405395, radius: 10.0 },
  { type: 'SpotROI', name: 'S_edge', emissivity: 0.3, x: 12.5, y: 6.25, radius: 14.0 },
  { type: 'PolygonROI', name: 'P_tri', emissivity: 0.85, points: [[72.46779809406465, 97.54798382036537], [116.82994020022844, 228.1873534201693], [191.86924988798958, 114.63453028863228]] },
  { type: 'PolygonROI', name: 'P_below', emissivity: 0.95, points: [[10.0, 200.0], [120.0, 190.0], [60.0, 400.0]] },
];

interface RefRoi {
  name: string; pixels: number; maskChecksum: number;
  min: number | null; max: number | null; mean: number | null; median: number | null; std: number | null;
}

function referenceFor(name: string): { rois: RefRoi[] } {
  const path = join(REFS, `${name}.rois.json`);
  if (!existsSync(path)) {
    mkdirSync(REFS, { recursive: true });
    const fixture = join(REFS, `${name}.fixture.json`);
    writeFileSync(fixture, JSON.stringify(ROI_FIXTURE));
    console.log('  generating ROI reference via desktop controller…');
    execFileSync(PYTHON, [join(import.meta.dirname, 'python_roi_reference.py'),
      join(SAMPLES, `${name}.jpg`), fixture, path], { stdio: 'inherit' });
  }
  return JSON.parse(readFileSync(path, 'utf8'));
}

const IMAGES = ['FLIR0135', 'flir_20250428T191100'];

for (const name of IMAGES) {
  console.log(`\n${name}.jpg`);
  const ref = referenceFor(name);
  const parsed = parseThermalImage(new Uint8Array(readFileSync(join(SAMPLES, `${name}.jpg`))));
  const params = parametersFromMetadata(parsed.metadata);

  // The desktop feeds a fraction into a percent-based correction term (HANDOFF §4),
  // so every desktop temperature carries this fixed offset. Subtracted, not hidden.
  const desktopBias = (params.RelativeHumidity / 100 - params.RelativeHumidity) * 0.00002;

  const rois: Roi[] = ROI_FIXTURE.map((r, i) => ({
    ...(r as any), id: `fixture-${i}`, color: 'hsl(0, 80%, 60%)',
  }));

  for (let i = 0; i < rois.length; i++) {
    const roi = rois[i];
    const expected = ref.rois[i];
    const indices = roiMaskIndices(roi, parsed.width, parsed.height);
    let checksum = 0;
    for (const v of indices) checksum += v;

    check(`${expected.name} mask`, indices.length === expected.pixels && checksum === expected.maskChecksum,
      `${indices.length} px / checksum ${checksum}, expected ${expected.pixels} / ${expected.maskChecksum}`);

    const stats = roiStatistics(roi, parsed.raw, parsed.width, parsed.height, params);
    if (expected.min === null) {
      check(`${expected.name} has no statistics`, stats === null || stats.pixels === 0);
      continue;
    }
    if (!stats) { check(`${expected.name} statistics`, false, 'got null'); continue; }

    const near = (got: number, want: number | null) => want !== null && Math.abs(got - (want - desktopBias)) <= TOL;
    check(`${expected.name} min/max`, near(stats.min, expected.min) && near(stats.max, expected.max),
      `${stats.min}/${stats.max} vs ${expected.min}/${expected.max}`);
    check(`${expected.name} mean/median`, near(stats.mean, expected.mean) && near(stats.median, expected.median),
      `${stats.mean}/${stats.median} vs ${expected.mean}/${expected.median}`);
    // The bias is a constant offset, so it cancels in the standard deviation.
    check(`${expected.name} std`, Math.abs(stats.std - (expected.std ?? NaN)) <= TOL,
      `${stats.std} vs ${expected.std}`);
  }
}

// --- Session schema ----------------------------------------------------------
console.log('\nsession sidecar');

const desktopSidecar = JSON.parse(readFileSync(join(SAMPLES, 'FLIR0135.json'), 'utf8'));
const imported = parseSession(desktopSidecar);
check('reads a desktop sidecar', imported.rois?.length === 3 && imported.palette === 'Bone');
check('overlay alignment', imported.alignment?.offsetX === -10 && Math.abs((imported.alignment?.scale ?? 0) - 0.861) < 1e-9);
check('opacity 100 → 1.0', imported.opacity === 1);
check('humidity fraction → percent', Math.abs((imported.parameters?.RelativeHumidity ?? 0) - 50) < 1e-9);

const state = {
  parameters: {
    Emissivity: 0.93, ReflectedApparentTemperature: 19.5, AtmosphericTemperature: 21.25,
    AtmosphericTransmission: 0.95, RelativeHumidity: 55,
    PlanckR1: 1, PlanckR2: 1, PlanckB: 1, PlanckF: 1, PlanckO: 1,
  },
  objectDistance: 2.5, palette: 'Iron', inverted: true, autoRange: false,
  manualMin: -3.5, manualMax: 88.25, showVisible: true, blend: 'HardLight' as const,
  opacity: 0.42, alignment: { ...DEFAULT_ALIGNMENT, scale: 1.3, offsetX: 7, offsetY: -4 },
  labels: { ...DEFAULT_LABEL_SETTINGS, median: true },
  rois: ROI_FIXTURE.map((r, i) => ({ ...(r as any), id: `x${i}`, color: 'hsl(0, 80%, 60%)' })) as Roi[],
};

const round = parseSession(JSON.parse(JSON.stringify(buildSession(state))));
check('round trip: parameters', round.parameters?.Emissivity === 0.93 && round.parameters?.RelativeHumidity === 55);
check('round trip: range', round.autoRange === false && round.manualMin === -3.5 && round.manualMax === 88.25);
check('round trip: overlay', round.blend === 'HardLight' && round.opacity === 0.42 && round.alignment?.offsetY === -4);
check('round trip: labels', round.labels?.median === true);
check('round trip: rois', JSON.stringify(round.rois?.map((r) => [r.type, r.name, r.emissivity]))
  === JSON.stringify(state.rois.map((r) => [r.type, r.name, r.emissivity])));

const csvCtx = { image: 'x.jpg', folder: 'x', datetime: null, gps: null, camera: null, width: 640, height: 480 };
const csvRows: AreaRow[] = state.rois.map((roi) => ({
  ctx: csvCtx, roi, stats: null, params: state.parameters as AreaRow['params'], objectDistance: 1,
}));
const csv = buildAreeCsv(csvRows);
check('aree.csv: BOM + header + one row per ROI',
  csv.charCodeAt(0) === 0xfeff && csv.trimEnd().split('\r\n').length === state.rois.length + 1);
check('aree.csv: semicolons, comma decimals', csv.includes(';Rettangolo;') && /0,\d/.test(csv));

console.log(failures ? `\n${failures} check(s) failed` : '\nPhase 3 passed: all checks green');
process.exit(failures ? 1 : 0);
