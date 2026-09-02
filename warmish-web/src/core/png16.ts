/**
 * Minimal PNG decoder for the single case FLIR uses for RawThermalImage:
 * 16-bit grayscale, non-interlaced. Returns raw samples in file (big-endian) order.
 *
 * A full image decoder is deliberately avoided here: the browser's native decoder
 * routes through an 8-bit canvas and would silently destroy radiometric precision.
 */
import { unzlibSync } from 'fflate';

export interface Png16 {
  width: number;
  height: number;
  /** One sample per pixel, big-endian order as stored in the PNG stream. */
  samples: Uint16Array;
}

const SIG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

export function decodePng16Gray(bytes: Uint8Array): Png16 {
  for (let i = 0; i < 8; i++) {
    if (bytes[i] !== SIG[i]) throw new Error('Not a PNG stream');
  }
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idat: Uint8Array[] = [];

  let p = 8;
  while (p + 8 <= bytes.length) {
    const len = dv.getUint32(p);
    const type = String.fromCharCode(bytes[p + 4], bytes[p + 5], bytes[p + 6], bytes[p + 7]);
    const body = p + 8;
    if (type === 'IHDR') {
      width = dv.getUint32(body);
      height = dv.getUint32(body + 4);
      bitDepth = bytes[body + 8];
      colorType = bytes[body + 9];
      if (bytes[body + 12] !== 0) throw new Error('Interlaced PNG not supported');
    } else if (type === 'IDAT') {
      idat.push(bytes.subarray(body, body + len));
    } else if (type === 'IEND') {
      break;
    }
    p = body + len + 4; // + CRC
  }

  if (bitDepth !== 16 || colorType !== 0) {
    throw new Error(`Expected 16-bit grayscale PNG, got depth=${bitDepth} colorType=${colorType}`);
  }

  const raw = unzlibSync(concat(idat));
  const bpp = 2; // bytes per pixel for 16-bit gray
  const stride = width * bpp;
  const out = new Uint8Array(height * stride);

  // Undo per-scanline filters (PNG spec §9.2).
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1;
    const dst = y * stride;
    const up = dst - stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[dst + x - bpp] : 0;
      const b = y > 0 ? out[up + x] : 0;
      const c = x >= bpp && y > 0 ? out[up + x - bpp] : 0;
      const v = raw[src + x];
      switch (filter) {
        case 0: out[dst + x] = v; break;
        case 1: out[dst + x] = v + a; break;
        case 2: out[dst + x] = v + b; break;
        case 3: out[dst + x] = v + ((a + b) >> 1); break;
        case 4: out[dst + x] = v + paeth(a, b, c); break;
        default: throw new Error(`Unknown PNG filter ${filter}`);
      }
    }
  }

  const samples = new Uint16Array(width * height);
  for (let i = 0; i < samples.length; i++) {
    samples[i] = (out[i * 2] << 8) | out[i * 2 + 1];
  }
  return { width, height, samples };
}

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  return pb <= pc ? b : c;
}

function concat(parts: Uint8Array[]): Uint8Array {
  let n = 0;
  for (const q of parts) n += q.length;
  const out = new Uint8Array(n);
  let o = 0;
  for (const q of parts) { out.set(q, o); o += q.length; }
  return out;
}
