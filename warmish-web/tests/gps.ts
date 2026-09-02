/**
 * GPS gate: `parseGps` must recover the coordinates ExifTool reports for the
 * sample images, straight from the JPEG bytes — no ExifTool at runtime.
 *
 *   npx tsx tests/gps.ts
 *
 * Expected values are ExifTool's own `-n` output for `exemple img/`.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { parseGps } from '../src/core/exif';

const SAMPLES = resolve(import.meta.dirname, '../../exemple img');

interface Expect {
  lat: number;
  lon: number;
  altitude: number | null;
  direction: number | null;
}

const EXPECTED: Record<string, Expect | null> = {
  'FLIR0135.jpg': { lat: 42.8513, lon: 13.57316667, altitude: 208, direction: null },
  'FLIR0354.jpg': { lat: 42.8513, lon: 13.57305, altitude: 217.9, direction: null },
  'IR_30-06-2026_0004.jpg': null,
  'IR_30-06-2026_0078.jpg': { lat: 42.85373333, lon: 13.58216667, altitude: 163, direction: null },
  'flir_20250428T191100.jpg': { lat: 42.84955, lon: 13.58766667, altitude: null, direction: 0 },
  'flir_20250811T121654.jpg': { lat: 42.09423333, lon: 14.6927, altitude: null, direction: 0 },
};

let failures = 0;
const check = (label: string, ok: boolean, detail = ''): void => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : ` — ${detail}`}`);
  if (!ok) failures++;
};

for (const [name, want] of Object.entries(EXPECTED)) {
  console.log(`\n${name}`);
  const fix = parseGps(new Uint8Array(readFileSync(join(SAMPLES, name))));

  if (want === null) {
    check('no GPS fix', fix === null, `got ${JSON.stringify(fix)}`);
    continue;
  }
  if (!fix) {
    check('GPS fix present', false, 'parseGps returned null');
    continue;
  }
  check('latitude', Math.abs(fix.lat - want.lat) < 1e-4, `${fix.lat} vs ${want.lat}`);
  check('longitude', Math.abs(fix.lon - want.lon) < 1e-4, `${fix.lon} vs ${want.lon}`);
  check(
    'altitude',
    want.altitude === null ? fix.altitude === null : fix.altitude !== null && Math.abs(fix.altitude - want.altitude) < 1,
    `${fix.altitude} vs ${want.altitude}`,
  );
  check(
    'direction',
    want.direction === null ? fix.direction === null : fix.direction === want.direction,
    `${fix.direction} vs ${want.direction}`,
  );
}

console.log(failures ? `\n${failures} check(s) failed` : '\nGPS gate passed');
process.exit(failures ? 1 : 0);
