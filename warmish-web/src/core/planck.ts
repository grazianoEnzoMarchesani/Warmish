/**
 * Planck inversion + environmental correction.
 * Direct translation of `_calculate_temperatures_from_raw` and
 * `_apply_environmental_correction` in core/thermal_engine.py.
 */
import type { FlirMetadata } from './flir';

export interface ThermalParameters {
  Emissivity: number;
  ReflectedApparentTemperature: number;
  AtmosphericTemperature: number;
  AtmosphericTransmission: number;
  RelativeHumidity: number;
  PlanckR1: number;
  PlanckR2: number;
  PlanckB: number;
  PlanckF: number;
  PlanckO: number;
}

export const DEFAULT_PARAMETERS = {
  Emissivity: 0.95,
  ReflectedApparentTemperature: 20.0,
  AtmosphericTemperature: 20.0,
  AtmosphericTransmission: 0.95,
  RelativeHumidity: 50.0,
};

/** Seeds the editable parameter panel from the file's own calibration data. */
export function parametersFromMetadata(m: FlirMetadata): ThermalParameters {
  return {
    Emissivity: finite(m.Emissivity, DEFAULT_PARAMETERS.Emissivity),
    ReflectedApparentTemperature: finite(m.ReflectedApparentTemperature, DEFAULT_PARAMETERS.ReflectedApparentTemperature),
    AtmosphericTemperature: finite(m.AtmosphericTemperature, DEFAULT_PARAMETERS.AtmosphericTemperature),
    AtmosphericTransmission: DEFAULT_PARAMETERS.AtmosphericTransmission,
    RelativeHumidity: finite(m.RelativeHumidity, DEFAULT_PARAMETERS.RelativeHumidity),
    PlanckR1: m.PlanckR1,
    PlanckR2: m.PlanckR2,
    PlanckB: m.PlanckB,
    PlanckF: m.PlanckF,
    PlanckO: m.PlanckO,
  };
}

/**
 * Builds the per-pixel inversion for one parameter set. Everything that does not
 * depend on the pixel is hoisted, so ROI recomputation with a different
 * emissivity costs no more than the pixels it actually touches.
 */
export function planckInverter(p: ThermalParameters): (raw: number) => number {
  const { PlanckR1: R1, PlanckR2: R2, PlanckB: B, PlanckF: F, PlanckO: O } = p;
  const emissivity = p.Emissivity;
  const reflK = p.ReflectedApparentTemperature + 273.15;

  const rawRefl = R1 / (R2 * (Math.exp(B / reflK) - F)) - O;
  const eps = Math.max(emissivity, 1e-6);
  const correction = environmentalCorrection(p);

  return (raw: number) => {
    const rawObj = (raw - (1 - emissivity) * rawRefl) / eps;
    const logArg = R1 / (R2 * (rawObj + O)) + F;
    return logArg > 0 ? B / Math.log(logArg) - 273.15 + correction : NaN;
  };
}

/** Raw sensor counts → °C. Pixels outside the Planck domain come back as NaN. */
export function computeTemperatures(raw: Uint16Array, p: ThermalParameters): Float64Array {
  const invert = planckInverter(p);
  const out = new Float64Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = invert(raw[i]);
  return out;
}

/** Same inversion restricted to a set of flat pixel indices — the ROI path. */
export function computeTemperaturesAt(
  raw: Uint16Array,
  indices: ArrayLike<number>,
  p: ThermalParameters,
): Float64Array {
  const invert = planckInverter(p);
  const out = new Float64Array(indices.length);
  for (let i = 0; i < indices.length; i++) out[i] = invert(raw[indices[i]]);
  return out;
}

/** The desktop app's empirical offset model — a scalar added to every pixel. */
export function environmentalCorrection(p: ThermalParameters): number {
  return (p.AtmosphericTemperature - 20.0) * 0.0005
    + (1.0 - p.AtmosphericTransmission) * 0.002
    + (p.RelativeHumidity - 50.0) * 0.00002;
}

export interface TemperatureRange { min: number; max: number }

export function temperatureRange(t: Float64Array): TemperatureRange {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < t.length; i++) {
    const v = t[i];
    if (Number.isNaN(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min === Infinity) return { min: 0, max: 0 };
  return { min, max };
}

/**
 * Central-percentile bounds — the display window that keeps the middle `pct` %
 * of the pixels and clips the tails, so a lone hot/cold pixel (a specular
 * reflection, a sun glint) can't flatten the contrast of the rest of the scene.
 * This is the classic linear percentile stretch; the temperature→colour mapping
 * stays linear, only the endpoints move.
 *
 * O(n) via a fine histogram + CDF (no sort), with linear interpolation inside
 * the straddling bin. Falls back to the full range when the result would be
 * degenerate (a near-uniform frame) or the inputs make no sense.
 */
export function percentileRange(t: Float64Array, pct: number): TemperatureRange {
  const full = temperatureRange(t);
  const span = full.max - full.min;
  if (!(span > 0) || !(pct > 0) || pct >= 100) return full;

  const BINS = 1024;
  const bins = new Uint32Array(BINS);
  let n = 0;
  for (let i = 0; i < t.length; i++) {
    const v = t[i];
    if (Number.isNaN(v)) continue;
    let b = Math.floor(((v - full.min) / span) * BINS);
    if (b < 0) b = 0; else if (b >= BINS) b = BINS - 1;
    bins[b]++;
    n++;
  }
  if (n === 0) return full;

  const tail = (n * (100 - pct)) / 200; // pixels to drop off each end
  let acc = 0;
  let lo = full.min;
  for (let b = 0; b < BINS; b++) {
    if (acc + bins[b] > tail) {
      lo = full.min + ((b + (bins[b] ? (tail - acc) / bins[b] : 0)) / BINS) * span;
      break;
    }
    acc += bins[b];
  }
  acc = 0;
  let hi = full.max;
  for (let b = BINS - 1; b >= 0; b--) {
    if (acc + bins[b] > tail) {
      hi = full.min + ((b + 1 - (bins[b] ? (tail - acc) / bins[b] : 0)) / BINS) * span;
      break;
    }
    acc += bins[b];
  }

  if (!(hi - lo > span / 1000)) return full;
  return { min: lo, max: hi };
}

function finite(v: number, fallback: number): number {
  return Number.isFinite(v) ? v : fallback;
}
