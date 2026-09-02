/**
 * Palette application. At runtime this is an indexed lookup into a precomputed
 * 256x3 table — the matplotlib colormap math happens offline in
 * tools/generate_palettes.py, not here.
 */
import palettesB64 from './palettes.json';

export type PaletteName = keyof typeof palettesB64 & string;

const cache = new Map<string, Uint8Array>();

export const PALETTE_NAMES = Object.keys(palettesB64) as PaletteName[];
export const DEFAULT_PALETTE: PaletteName = 'Iron';

/** Flat [R0,G0,B0, R1,...] table, 768 bytes. */
export function getLut(name: string): Uint8Array {
  let lut = cache.get(name);
  if (lut) return lut;
  const b64 = (palettesB64 as Record<string, string>)[name] ?? (palettesB64 as Record<string, string>)[DEFAULT_PALETTE];
  const bin = atob(b64);
  lut = new Uint8Array(768);
  for (let i = 0; i < 768; i++) lut[i] = bin.charCodeAt(i);
  cache.set(name, lut);
  return lut;
}

export interface ColorizeOptions {
  palette: string;
  inverted: boolean;
  /** Display range; defaults to the data range. */
  min: number;
  max: number;
}

/**
 * Temperatures (°C) -> RGBA pixels, matching `create_colored_pixmap`:
 * normalize over [min, max], NaN collapses to 0, index = floor(norm * 256).
 */
export function colorize(temps: Float64Array, opts: ColorizeOptions): Uint8ClampedArray {
  const lut = getLut(opts.palette);
  const span = opts.max - opts.min === 0 ? 1 : opts.max - opts.min;
  const out = new Uint8ClampedArray(temps.length * 4);

  for (let i = 0; i < temps.length; i++) {
    let norm = (temps[i] - opts.min) / span;
    if (!Number.isFinite(norm)) norm = 0;
    if (opts.inverted) norm = 1.0 - norm;
    let idx = Math.floor(norm * 256);
    if (idx < 0) idx = 0;
    else if (idx > 255) idx = 255;
    const o = i * 4;
    const l = idx * 3;
    out[o] = lut[l];
    out[o + 1] = lut[l + 1];
    out[o + 2] = lut[l + 2];
    out[o + 3] = 255;
  }
  return out;
}
