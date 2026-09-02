/**
 * Minimal standard-EXIF reader. `flir.ts` decodes the radiometric FLIR APP1
 * blob; this pulls the ordinary TIFF/EXIF tags (camera make, lens, exposure,
 * GPS, timestamps…) out of the JPEG so the UI can show "everything the camera
 * wrote about this frame". Presentation only — nothing here feeds the pipeline.
 */

export interface ExifEntry {
  tag: string;
  value: string;
}

const IFD0: Record<number, string> = {
  0x0100: 'ImageWidth', 0x0101: 'ImageHeight', 0x0102: 'BitsPerSample',
  0x0103: 'Compression', 0x0106: 'PhotometricInterpretation',
  0x010e: 'ImageDescription', 0x010f: 'Make', 0x0110: 'Model',
  0x0112: 'Orientation', 0x0115: 'SamplesPerPixel', 0x011a: 'XResolution',
  0x011b: 'YResolution', 0x0128: 'ResolutionUnit', 0x0131: 'Software',
  0x0132: 'DateTime', 0x013b: 'Artist', 0x013e: 'WhitePoint',
  0x0213: 'YCbCrPositioning', 0x8298: 'Copyright',
  // EXIF sub-IFD (tag 0x829a onward live under ExifOffset)
  0x829a: 'ExposureTime', 0x829d: 'FNumber', 0x8822: 'ExposureProgram',
  0x8827: 'ISO', 0x9000: 'ExifVersion', 0x9003: 'DateTimeOriginal',
  0x9004: 'DateTimeDigitized', 0x9201: 'ShutterSpeedValue',
  0x9202: 'ApertureValue', 0x9203: 'BrightnessValue',
  0x9204: 'ExposureCompensation', 0x9205: 'MaxApertureValue',
  0x9206: 'SubjectDistance', 0x9207: 'MeteringMode', 0x9208: 'LightSource',
  0x9209: 'Flash', 0x920a: 'FocalLength', 0x9101: 'ComponentsConfiguration',
  0x9102: 'CompressedBitsPerPixel', 0x9286: 'UserComment', 0x9290: 'SubSecTime',
  0x9291: 'SubSecTimeOriginal', 0x9292: 'SubSecTimeDigitized',
  0xa000: 'FlashpixVersion', 0xa001: 'ColorSpace', 0xa002: 'PixelXDimension',
  0xa003: 'PixelYDimension', 0xa402: 'ExposureMode', 0xa403: 'WhiteBalance',
  0xa404: 'DigitalZoomRatio', 0xa405: 'FocalLengthIn35mmFilm',
  0xa406: 'SceneCaptureType', 0xa420: 'ImageUniqueID', 0xa430: 'CameraOwnerName',
  0xa431: 'BodySerialNumber', 0xa432: 'LensSpecification',
  0xa433: 'LensMake', 0xa434: 'LensModel', 0xa435: 'LensSerialNumber',
  0xa500: 'Gamma',
};

/** Vendor-private binary blobs — always shown as raw bytes, never useful here. */
const SKIP = new Set([0x927c /* MakerNote */]);

const GPS: Record<number, string> = {
  0x0000: 'VersionID', 0x0001: 'LatitudeRef', 0x0002: 'Latitude',
  0x0003: 'LongitudeRef', 0x0004: 'Longitude', 0x0005: 'AltitudeRef',
  0x0006: 'Altitude', 0x0007: 'TimeStamp', 0x0008: 'Satellites',
  0x0009: 'Status', 0x000a: 'MeasureMode', 0x000b: 'DOP',
  0x0010: 'ImgDirectionRef', 0x0011: 'ImgDirection', 0x0012: 'MapDatum',
  0x001d: 'DateStamp',
};

const TYPE_SIZE: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 };

/** Returns the TIFF payload of the "Exif\0\0" APP1 segment, or null. */
function findExifTiff(jpeg: Uint8Array): Uint8Array | null {
  const dv = new DataView(jpeg.buffer, jpeg.byteOffset, jpeg.byteLength);
  if (dv.getUint16(0) !== 0xffd8) return null;
  let p = 2;
  while (p + 4 <= jpeg.length) {
    if (jpeg[p] !== 0xff) { p++; continue; }
    const marker = jpeg[p + 1];
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { p += 2; continue; }
    if (marker === 0xda || marker === 0xd9) break;
    const len = dv.getUint16(p + 2);
    const seg = jpeg.subarray(p + 4, p + 2 + len);
    if (marker === 0xe1 && seg.length > 6 && str(seg, 0, 4) === 'Exif' && seg[4] === 0) {
      return seg.subarray(6);
    }
    p += 2 + len;
  }
  return null;
}

/** Byte span of the `FF E1 … "Exif\0\0" …` APP1 segment, marker included. */
function findApp1Span(jpeg: Uint8Array): { start: number; end: number } | null {
  const dv = new DataView(jpeg.buffer, jpeg.byteOffset, jpeg.byteLength);
  if (dv.getUint16(0) !== 0xffd8) return null;
  let p = 2;
  while (p + 4 <= jpeg.length) {
    if (jpeg[p] !== 0xff) { p++; continue; }
    const marker = jpeg[p + 1];
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { p += 2; continue; }
    if (marker === 0xda || marker === 0xd9) break;
    const len = dv.getUint16(p + 2);
    if (marker === 0xe1) {
      const seg = jpeg.subarray(p + 4, p + 2 + len);
      if (seg.length > 6 && str(seg, 0, 4) === 'Exif' && seg[4] === 0) return { start: p, end: p + 2 + len };
    }
    p += 2 + len;
  }
  return null;
}

/**
 * The whole APP1 EXIF segment (marker and length included), or null. Used to
 * lift the camera's EXIF off the parent JPEG for the bare visible frame that
 * lives inside the FLIR container.
 */
export function extractExifApp1(jpeg: Uint8Array): Uint8Array | null {
  const span = findApp1Span(jpeg);
  return span ? jpeg.slice(span.start, span.end) : null;
}

/**
 * Grafts the parent's APP1 EXIF onto a JPEG, **replacing** any APP1 the JPEG
 * already carries — the embedded visible frame ships a stub EXIF with neither
 * GPS nor timestamp, and the parent block is the authoritative one.
 */
export function injectExifApp1(jpeg: Uint8Array, app1: Uint8Array | null): Uint8Array {
  if (!app1 || jpeg[0] !== 0xff || jpeg[1] !== 0xd8) return jpeg;
  const span = findApp1Span(jpeg);
  const at = span ? span.start : 2;
  const after = span ? span.end : 2;
  const out = new Uint8Array(at + app1.length + (jpeg.length - after));
  out.set(jpeg.subarray(0, at), 0);
  out.set(app1, at);
  out.set(jpeg.subarray(after), at + app1.length);
  return out;
}

export interface CaptureInfo {
  /** "Make Model", or whichever half exists, or null. */
  camera: string | null;
  /** `YYYY-MM-DD HH:MM:SS` local (naive), or null. */
  datetime: string | null;
}

/** Camera model and capture time, for the CSV and the manifest. */
export function parseCapture(jpeg: Uint8Array): CaptureInfo {
  const entries = parseExif(jpeg);
  const get = (t: string) => entries.find((e) => e.tag === t)?.value || null;
  const make = get('Make');
  const model = get('Model');
  let camera: string | null = null;
  if (model) camera = make && !model.startsWith(make) ? `${make} ${model}` : model;
  else camera = make;
  // "Teledyne FLIR" + "FLIR T530" → collapse the repeated word.
  if (camera) camera = camera.replace(/\b(\w+)\s+\1\b/gi, '$1');
  const raw = get('DateTimeOriginal') || get('DateTime') || get('DateTimeDigitized');
  const datetime = raw ? raw.replace(/^(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3') : null;
  return { camera, datetime };
}

export function parseExif(jpeg: Uint8Array): ExifEntry[] {
  const tiff = findExifTiff(jpeg);
  if (!tiff || tiff.length < 8) return [];
  const dv = new DataView(tiff.buffer, tiff.byteOffset, tiff.byteLength);
  const le = str(tiff, 0, 2) === 'II';
  const u16 = (o: number) => dv.getUint16(o, le);
  const u32 = (o: number) => dv.getUint32(o, le);
  if (u16(2) !== 42) return [];

  const out: ExifEntry[] = [];
  const seen = new Set<number>();

  const walk = (ifdOff: number, names: Record<number, string>, prefix: string): void => {
    if (ifdOff < 8 || ifdOff + 2 > tiff.length || seen.has(ifdOff)) return;
    seen.add(ifdOff);
    const count = u16(ifdOff);
    for (let i = 0; i < count; i++) {
      const e = ifdOff + 2 + i * 12;
      if (e + 12 > tiff.length) break;
      const tag = u16(e);
      const type = u16(e + 2);
      const num = u32(e + 4);
      if (tag === 0x8769) { walk(u32(e + 8), IFD0, ''); continue; }   // ExifOffset
      if (tag === 0x8825) { walk(u32(e + 8), GPS, 'GPS'); continue; } // GPSInfo
      if (SKIP.has(tag)) continue;
      const size = TYPE_SIZE[type];
      if (!size || num > 0x10000) continue;
      const bytes = size * num;
      const vOff = bytes <= 4 ? e + 8 : u32(e + 8);
      if (vOff + bytes > tiff.length) continue;
      const name = (prefix ? `${prefix}.` : '') + (names[tag] ?? `Tag 0x${tag.toString(16).padStart(4, '0')}`);
      let value = format(dv, tiff, vOff, type, num, le);
      if (value.length > 160) value = `${value.slice(0, 160)}…`;
      if (value !== '') out.push({ tag: name, value });
    }
  };

  walk(u32(4), IFD0, '');
  return out;
}

function format(dv: DataView, tiff: Uint8Array, o: number, type: number, num: number, le: boolean): string {
  if (type === 2) { // ASCII
    let s = '';
    for (let i = 0; i < num; i++) { const c = tiff[o + i]; if (c === 0) break; s += String.fromCharCode(c); }
    return s.trim();
  }
  if (type === 7 || type === 1) { // UNDEFINED / BYTE
    let printable = true;
    const codes: number[] = [];
    for (let i = 0; i < num; i++) {
      const c = tiff[o + i];
      codes.push(c);
      if (c !== 0 && (c < 0x20 || c > 0x7e)) printable = false;
    }
    if (printable && codes.some((c) => c !== 0)) {
      return String.fromCharCode(...codes.filter((c) => c !== 0)).trim();
    }
    return codes.join(' ');
  }
  const vals: number[] = [];
  for (let i = 0; i < num; i++) {
    switch (type) {
      case 3: vals.push(dv.getUint16(o + i * 2, le)); break;
      case 4: vals.push(dv.getUint32(o + i * 4, le)); break;
      case 9: vals.push(dv.getInt32(o + i * 4, le)); break;
      case 5: { const n = dv.getUint32(o + i * 8, le), d = dv.getUint32(o + i * 8 + 4, le); vals.push(d ? n / d : 0); break; }
      case 10: { const n = dv.getInt32(o + i * 8, le), d = dv.getInt32(o + i * 8 + 4, le); vals.push(d ? n / d : 0); break; }
      default: return '';
    }
  }
  return vals.map((v) => (Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/\.?0+$/, ''))).join(', ');
}

function str(a: Uint8Array, start: number, len: number): string {
  let s = '';
  for (let i = 0; i < len; i++) s += String.fromCharCode(a[start + i]);
  return s;
}

// --- GPS -------------------------------------------------------------------
// `parseExif` above turns every tag into a display string; the map view needs
// the GPS fix as plain numbers. This is a second, focused pass over the same
// TIFF: walk IFD0 to the GPSInfo pointer, then read only the tags a map uses.

export interface GpsFix {
  /** Signed decimal degrees (negative = south). */
  lat: number;
  /** Signed decimal degrees (negative = west). */
  lon: number;
  /** Metres, signed (negative = below sea level), or null if absent. */
  altitude: number | null;
  /** Camera bearing in degrees, 0–360, or null if absent. 0 is a valid value. */
  direction: number | null;
  /** 'T' true north, 'M' magnetic north, or null. */
  directionRef: 'T' | 'M' | null;
  /** e.g. "WGS84", or null. */
  mapDatum: string | null;
}

export function parseGps(jpeg: Uint8Array): GpsFix | null {
  const tiff = findExifTiff(jpeg);
  if (!tiff || tiff.length < 8) return null;
  const dv = new DataView(tiff.buffer, tiff.byteOffset, tiff.byteLength);
  const le = str(tiff, 0, 2) === 'II';
  const u16 = (o: number) => dv.getUint16(o, le);
  const u32 = (o: number) => dv.getUint32(o, le);
  if (u16(2) !== 42) return null;

  // Locate the GPSInfo sub-IFD via tag 0x8825 in IFD0.
  const ifd0 = u32(4);
  if (ifd0 < 8 || ifd0 + 2 > tiff.length) return null;
  let gpsOff = 0;
  const n0 = u16(ifd0);
  for (let i = 0; i < n0; i++) {
    const e = ifd0 + 2 + i * 12;
    if (e + 12 > tiff.length) break;
    if (u16(e) === 0x8825) { gpsOff = u32(e + 8); break; }
  }
  if (gpsOff < 8 || gpsOff + 2 > tiff.length) return null;

  const tags = new Map<number, { type: number; num: number; off: number }>();
  const nG = u16(gpsOff);
  for (let i = 0; i < nG; i++) {
    const e = gpsOff + 2 + i * 12;
    if (e + 12 > tiff.length) break;
    const type = u16(e + 2);
    const num = u32(e + 4);
    const size = TYPE_SIZE[type] ?? 0;
    if (!size || num > 0x1000) continue;
    const bytes = size * num;
    const off = bytes <= 4 ? e + 8 : u32(e + 8);
    if (off + bytes > tiff.length) continue;
    tags.set(u16(e), { type, num, off });
  }

  const rat = (o: number) => {
    const n = dv.getUint32(o, le);
    const d = dv.getUint32(o + 4, le);
    return d ? n / d : 0;
  };
  /** deg/min/sec triple of rationals → decimal degrees. */
  const dms = (tag: number): number | null => {
    const t = tags.get(tag);
    if (!t || t.type !== 5 || t.num < 3) return null;
    return rat(t.off) + rat(t.off + 8) / 60 + rat(t.off + 16) / 3600;
  };
  const rational1 = (tag: number): number | null => {
    const t = tags.get(tag);
    return t && t.type === 5 ? rat(t.off) : null;
  };
  const ascii = (tag: number): string | null => {
    const t = tags.get(tag);
    if (!t) return null;
    let s = '';
    for (let i = 0; i < t.num; i++) { const c = tiff[t.off + i]; if (c === 0) break; s += String.fromCharCode(c); }
    return s.trim() || null;
  };

  let lat = dms(0x0002);
  let lon = dms(0x0004);
  if (lat === null || lon === null) return null;
  if (ascii(0x0001) === 'S') lat = -lat;
  if (ascii(0x0003) === 'W') lon = -lon;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  // A camera with no fix commonly writes 0/0 — not a place anyone photographs.
  if (lat === 0 && lon === 0) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;

  let altitude = rational1(0x0006);
  const altRef = tags.get(0x0005);
  if (altitude !== null && altRef && tiff[altRef.off] === 1) altitude = -altitude;

  const direction = rational1(0x0011);
  const dRef = ascii(0x0010);

  return {
    lat,
    lon,
    altitude: altitude !== null && Number.isFinite(altitude) ? altitude : null,
    direction: direction !== null && Number.isFinite(direction) ? ((direction % 360) + 360) % 360 : null,
    directionRef: dRef === 'M' ? 'M' : dRef === 'T' ? 'T' : null,
    mapDatum: ascii(0x0012),
  };
}
