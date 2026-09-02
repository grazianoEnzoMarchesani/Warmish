/**
 * Phase-0 gate: the TypeScript core must reproduce the desktop app's numbers
 * without ExifTool, for every sample image.
 *
 *   npx tsx tests/phase0.ts
 *
 * References are produced by tests/python_reference.py driving the real
 * core/thermal_engine.py. Regenerate them if the desktop engine changes.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs';
import { join, basename, resolve } from 'node:path';

import { parseThermalImage } from '../src/core/flir';
import { computeTemperatures, parametersFromMetadata, percentileRange, temperatureRange } from '../src/core/planck';
import { colorize } from '../src/core/colormap';
import { alignmentFromMetadata } from '../src/core/render';

const REPO = resolve(import.meta.dirname, '../..');
const SAMPLES = join(REPO, 'exemple img');
const REFS = join(import.meta.dirname, 'reference');
const PYTHON = existsSync(join(REPO, 'venv/bin/python3')) ? join(REPO, 'venv/bin/python3') : 'python3';

const TOL_TEMP = 1e-6; // °C — float64 on both sides, so this is round-off only
const TOL_PARAM = 1e-3;

interface Reference {
  parameters: Record<string, number>;
  width: number;
  height: number;
  rawChecksum: number;
  tempMin: number;
  tempMax: number;
  tempMean: number;
  samples: { i: number; t: number | null }[];
  colorIndices: number[];
  colors: Record<string, number[][]>;
  overlay: { scale: number; offset_x: number; offset_y: number };
}

function referenceFor(name: string): Reference {
  const path = join(REFS, `${name}.json`);
  if (!existsSync(path)) {
    mkdirSync(REFS, { recursive: true });
    console.log(`  generating reference via desktop engine…`);
    execFileSync(PYTHON, [join(import.meta.dirname, 'python_reference.py'), join(SAMPLES, `${name}.jpg`), path], {
      stdio: 'inherit',
    });
  }
  return JSON.parse(readFileSync(path, 'utf8'));
}

let failures = 0;

function check(label: string, ok: boolean, detail = ''): void {
  if (ok) {
    console.log(`  ok   ${label}`);
  } else {
    failures++;
    console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

const images = readdirSync(SAMPLES).filter((f) => f.toLowerCase().endsWith('.jpg')).sort();
if (!images.length) throw new Error(`No sample images in ${SAMPLES}`);

for (const file of images) {
  const name = basename(file, '.jpg');
  console.log(`\n${file}`);
  const ref = referenceFor(name);

  const parsed = parseThermalImage(new Uint8Array(readFileSync(join(SAMPLES, file))));

  check('dimensions', parsed.width === ref.width && parsed.height === ref.height,
    `got ${parsed.width}x${parsed.height}, expected ${ref.width}x${ref.height}`);

  let sum = 0;
  for (const v of parsed.raw) sum += v;
  check('raw sensor data identical', sum === ref.rawChecksum, `checksum ${sum} vs ${ref.rawChecksum}`);

  const params = parametersFromMetadata(parsed.metadata);
  for (const key of ['PlanckR1', 'PlanckR2', 'PlanckB', 'PlanckF', 'PlanckO', 'Emissivity',
    'ReflectedApparentTemperature', 'AtmosphericTemperature'] as const) {
    const expected = ref.parameters[key];
    if (expected === undefined) continue;
    const got = params[key];
    check(`${key}`, Math.abs(got - expected) <= Math.abs(expected) * TOL_PARAM + 1e-9,
      `got ${got}, expected ${expected}`);
  }

  // The desktop app reads metadata through PyExifTool's `-n` mode, so it receives
  // RelativeHumidity as a fraction (0.5) and feeds it to a correction term written
  // for percent — a latent unit bug that biases every pixel by a fixed amount.
  // The web app uses percent (matching its own UI and the desktop's own default),
  // so the reference is offset by exactly that term before comparing.
  check('RelativeHumidity (desktop reports a fraction)',
    Math.abs(params.RelativeHumidity - ref.parameters.RelativeHumidity * 100) < 1e-6,
    `got ${params.RelativeHumidity}%, desktop ${ref.parameters.RelativeHumidity}`);
  const desktopBias = (ref.parameters.RelativeHumidity - params.RelativeHumidity) * 0.00002;

  // Computed from the parameters this parser derived — no values borrowed from the reference.
  const temps = computeTemperatures(parsed.raw, params);
  const range = temperatureRange(temps);
  check('temperature min', Math.abs(range.min - (ref.tempMin - desktopBias)) <= TOL_TEMP, `${range.min} vs ${ref.tempMin - desktopBias}`);
  check('temperature max', Math.abs(range.max - (ref.tempMax - desktopBias)) <= TOL_TEMP, `${range.max} vs ${ref.tempMax - desktopBias}`);

  // Percentile stretch: the central-98% window sits inside the true range, the
  // 90% window inside the 98% one, and a full 100% window is the range itself.
  const p98 = percentileRange(temps, 98);
  const p90 = percentileRange(temps, 90);
  check('stretch 98% is inside the true range',
    p98.min >= range.min - 1e-9 && p98.max <= range.max + 1e-9 && p98.max - p98.min < range.max - range.min,
    `${p98.min}–${p98.max} vs ${range.min}–${range.max}`);
  check('stretch 90% is tighter than 98%',
    p90.min >= p98.min - 1e-9 && p90.max <= p98.max + 1e-9);
  check('stretch 100% is the full range',
    Math.abs(percentileRange(temps, 100).min - range.min) < 1e-9);

  let worst = 0;
  let worstAt = -1;
  for (const s of ref.samples) {
    const got = temps[s.i];
    if (s.t === null) {
      if (!Number.isNaN(got)) { worst = Infinity; worstAt = s.i; }
      continue;
    }
    const d = Math.abs(got - (s.t - desktopBias));
    if (d > worst) { worst = d; worstAt = s.i; }
  }
  check(`${ref.samples.length} sampled pixels`, worst <= TOL_TEMP,
    `max deviation ${worst} at index ${worstAt}`);

  check('embedded visible image', parsed.visible !== null && parsed.visible[0] === 0xff,
    parsed.visible ? 'not a JPEG' : 'missing');

  // Overlay alignment must match what the desktop derives from the same metadata.
  const align = alignmentFromMetadata(parsed.metadata);
  check('overlay alignment (scale / offsets)',
    Math.abs(align.scale - ref.overlay.scale) < 1e-6
      && align.offsetX === ref.overlay.offset_x
      && align.offsetY === ref.overlay.offset_y,
    `got ${JSON.stringify(align)}, desktop ${JSON.stringify(ref.overlay)}`);

  // Palette LUTs must reproduce matplotlib exactly, including the index rounding.
  let paletteMismatch = '';
  for (const [name, expected] of Object.entries(ref.colors)) {
    const px = colorize(temps, { palette: name, inverted: false, min: range.min, max: range.max });
    ref.colorIndices.forEach((flat, k) => {
      const got = [px[flat * 4], px[flat * 4 + 1], px[flat * 4 + 2]];
      const want = expected[k];
      if (!paletteMismatch && (got[0] !== want[0] || got[1] !== want[1] || got[2] !== want[2])) {
        paletteMismatch = `${name}@${flat}: got ${got} expected ${want}`;
      }
    });
  }
  check(`palette LUTs (${Object.keys(ref.colors).length} palettes)`, !paletteMismatch, paletteMismatch);
}

console.log(failures ? `\n${failures} check(s) failed` : '\nPhase 0 passed: all checks green');
process.exit(failures ? 1 : 0);
