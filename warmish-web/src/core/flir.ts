/**
 * FLIR APP1 parser — replaces the ExifTool subprocess calls in core/thermal_engine.py.
 *
 * Layout (verified against ExifTool output for every file in `exemple img/`):
 *   JPEG APP1 segments carrying an 8-byte "FLIR\0" header are concatenated, ordered
 *   by the chunk index at byte 6, into a single FFF blob.
 *   FFF header: magic "FFF\0", big-endian index offset @0x18 and entry count @0x1c.
 *   Index entry (32 B, big-endian): mainType u16, subType u16, version u32,
 *   indexID u32, dataOffset u32, dataLength u32.
 *   Record payload fields are little-endian; image records carry a 0x20-byte header.
 */
import { decodePng16Gray } from './png16';

export const REC_RAW_DATA = 1;
export const REC_EMBEDDED_IMAGE = 14;
export const REC_CAMERA_INFO = 32;
export const REC_IMAGE_INFO = 42;

export interface FlirMetadata {
  PlanckR1: number;
  PlanckR2: number;
  PlanckB: number;
  PlanckF: number;
  PlanckO: number;
  Emissivity: number;
  ObjectDistance: number;
  /** Celsius — ExifTool reports these as °C; the file stores Kelvin. */
  ReflectedApparentTemperature: number;
  AtmosphericTemperature: number;
  IRWindowTemperature: number;
  IRWindowTransmission: number;
  /** Percent, matching ExifTool's presentation. */
  RelativeHumidity: number;
  AtmosphericTransAlpha1: number;
  AtmosphericTransAlpha2: number;
  AtmosphericTransBeta1: number;
  AtmosphericTransBeta2: number;
  AtmosphericTransX: number;
  RawThermalImageWidth: number;
  RawThermalImageHeight: number;
  RawThermalImageType: 'PNG' | 'TIFF';
  /**
   * Visible-to-IR field-of-view ratio (ExifTool's `Real2IR`), used to derive the
   * overlay's natural scale as `1 / Real2IR`. Defaults to 1 when the file carries
   * no ImageInfo record.
   */
  Real2IR: number;
  /** Thermal-vs-visible alignment offset, in visible-image pixels. Defaults to 0. */
  OffsetX: number;
  OffsetY: number;
}

export interface ThermalFile {
  metadata: FlirMetadata;
  width: number;
  height: number;
  /** Raw sensor counts, row-major, length width*height. */
  raw: Uint16Array;
  /** Embedded visible-light JPEG bytes, if the file carries one. */
  visible: Uint8Array | null;
}

interface IndexEntry { mainType: number; subType: number; offset: number; length: number }

/** Concatenates the FLIR APP1 chunks of a JPEG into the FFF blob. */
export function extractFff(jpeg: Uint8Array): Uint8Array {
  const dv = new DataView(jpeg.buffer, jpeg.byteOffset, jpeg.byteLength);
  if (dv.getUint16(0) !== 0xffd8) throw new Error('Not a JPEG file');

  const chunks: { index: number; data: Uint8Array }[] = [];
  let p = 2;
  while (p + 4 <= jpeg.length) {
    if (jpeg[p] !== 0xff) { p++; continue; }
    const marker = jpeg[p + 1];
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { p += 2; continue; }
    if (marker === 0xda || marker === 0xd9) break; // start of scan / end of image
    const len = dv.getUint16(p + 2);
    const seg = jpeg.subarray(p + 4, p + 2 + len);
    if (marker === 0xe1 && seg.length > 8 && str(seg, 0, 4) === 'FLIR') {
      chunks.push({ index: seg[6], data: seg.subarray(8) });
    }
    p += 2 + len;
  }
  if (!chunks.length) throw new Error('No FLIR APP1 data found — not a radiometric FLIR image');

  chunks.sort((a, b) => a.index - b.index);
  let total = 0;
  for (const c of chunks) total += c.data.length;
  const fff = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) { fff.set(c.data, o); o += c.data.length; }
  if (str(fff, 0, 4) !== 'FFF\0') throw new Error('FLIR APP1 data is not an FFF container');
  return fff;
}

function readIndex(fff: Uint8Array): IndexEntry[] {
  const dv = new DataView(fff.buffer, fff.byteOffset, fff.byteLength);
  const indexOffset = dv.getUint32(0x18);
  const count = dv.getUint32(0x1c);
  const entries: IndexEntry[] = [];
  for (let i = 0; i < count; i++) {
    const o = indexOffset + i * 32;
    if (o + 32 > fff.length) break;
    const e: IndexEntry = {
      mainType: dv.getUint16(o),
      subType: dv.getUint16(o + 2),
      offset: dv.getUint32(o + 12),
      length: dv.getUint32(o + 16),
    };
    // Unused index slots are zero-filled; entries past the payload are garbage.
    if (e.mainType === 0 || e.length === 0 || e.offset + e.length > fff.length) continue;
    entries.push(e);
  }
  return entries;
}

/** CameraInfo field offsets, confirmed by matching each value against ExifTool's report. */
function readCameraInfo(rec: Uint8Array): Omit<FlirMetadata, 'RawThermalImageWidth' | 'RawThermalImageHeight' | 'RawThermalImageType' | 'Real2IR' | 'OffsetX' | 'OffsetY'> {
  const dv = new DataView(rec.buffer, rec.byteOffset, rec.byteLength);
  const f = (o: number) => dv.getFloat32(o, true);
  // Values are kept at full float32 precision — the camera's 24.9999938964844 °C
  // must not be rounded here, because a low-emissivity scene amplifies the
  // reflected-temperature term. Rounding is a presentation concern only.
  return {
    Emissivity: f(0x20),
    ObjectDistance: f(0x24),
    ReflectedApparentTemperature: f(0x28) - 273.15,
    AtmosphericTemperature: f(0x2c) - 273.15,
    IRWindowTemperature: f(0x30) - 273.15,
    IRWindowTransmission: f(0x34),
    RelativeHumidity: f(0x3c) * 100,
    PlanckR1: f(0x58),
    PlanckB: f(0x5c),
    PlanckF: f(0x60),
    AtmosphericTransAlpha1: f(0x70),
    AtmosphericTransAlpha2: f(0x74),
    AtmosphericTransBeta1: f(0x78),
    AtmosphericTransBeta2: f(0x7c),
    AtmosphericTransX: f(0x80),
    PlanckO: dv.getInt32(0x308, true),
    PlanckR2: f(0x30c),
  };
}

/**
 * ImageInfo (record type 42) alignment fields, offsets confirmed against ExifTool
 * for every sample file: `Real2IR` float32 @ 0x00, then int16 `OffsetX`, `OffsetY`,
 * `PiPX1`, `PiPX2`, `PiPY1`, `PiPY2`. Only the first three drive the overlay.
 */
function readImageInfo(rec: Uint8Array): Pick<FlirMetadata, 'Real2IR' | 'OffsetX' | 'OffsetY'> {
  const dv = new DataView(rec.buffer, rec.byteOffset, rec.byteLength);
  return {
    Real2IR: dv.getFloat32(0x00, true),
    OffsetX: dv.getInt16(0x04, true),
    OffsetY: dv.getInt16(0x06, true),
  };
}

export function parseThermalImage(jpeg: Uint8Array): ThermalFile {
  const fff = extractFff(jpeg);
  const entries = readIndex(fff);

  const camEntry = entries.find((e) => e.mainType === REC_CAMERA_INFO);
  const rawEntry = entries.find((e) => e.mainType === REC_RAW_DATA);
  if (!camEntry) throw new Error('FLIR CameraInfo record missing');
  if (!rawEntry) throw new Error('FLIR RawData record missing');

  const camera = readCameraInfo(fff.subarray(camEntry.offset, camEntry.offset + camEntry.length));

  const rawRec = fff.subarray(rawEntry.offset, rawEntry.offset + rawEntry.length);
  const rdv = new DataView(rawRec.buffer, rawRec.byteOffset, rawRec.byteLength);
  const width = rdv.getUint16(2, true);
  const height = rdv.getUint16(4, true);
  const payload = rawRec.subarray(0x20);

  let raw: Uint16Array;
  let type: 'PNG' | 'TIFF';
  if (payload[0] === 0x89 && payload[1] === 0x50) {
    type = 'PNG';
    const png = decodePng16Gray(payload);
    // FLIR stores the 16-bit samples little-endian inside a spec-big-endian PNG,
    // so a spec-compliant decode must be byte-swapped (the desktop app does the
    // same via numpy's byteswap after PIL decode).
    raw = new Uint16Array(png.samples.length);
    for (let i = 0; i < raw.length; i++) {
      const v = png.samples[i];
      raw[i] = ((v & 0xff) << 8) | (v >> 8);
    }
  } else {
    type = 'TIFF';
    raw = new Uint16Array(width * height);
    const pdv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    for (let i = 0; i < raw.length; i++) raw[i] = pdv.getUint16(i * 2, true);
  }

  const infoEntry = entries.find((e) => e.mainType === REC_IMAGE_INFO);
  const imageInfo = infoEntry
    ? readImageInfo(fff.subarray(infoEntry.offset, infoEntry.offset + infoEntry.length))
    : { Real2IR: 1, OffsetX: 0, OffsetY: 0 };

  const embedded = entries.find((e) => e.mainType === REC_EMBEDDED_IMAGE);
  let visible: Uint8Array | null = null;
  if (embedded) {
    const rec = fff.subarray(embedded.offset, embedded.offset + embedded.length);
    const body = rec.subarray(0x20);
    if (body[0] === 0xff && body[1] === 0xd8) visible = body;
  }

  return {
    metadata: {
      ...camera,
      RawThermalImageWidth: width,
      RawThermalImageHeight: height,
      RawThermalImageType: type,
      ...imageInfo,
    },
    width,
    height,
    raw,
    visible,
  };
}

function str(a: Uint8Array, start: number, len: number): string {
  let s = '';
  for (let i = 0; i < len; i++) s += String.fromCharCode(a[start + i]);
  return s;
}
