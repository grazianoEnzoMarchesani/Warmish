# Warmish Web — handoff

Written for whoever (or whatever) picks this up next. Everything here is verified,
not assumed; where something is unverified it says so.

Repo root is the existing PySide6 desktop app. All new work lives in `warmish-web/`
and touches **nothing** outside it.

---

## 1. Why this exists

The desktop app fails to launch on some Macs. Root cause: it ships `exiftool_bin`,
which is literally ExifTool's Perl script, and the PyInstaller build is unsigned
(`Warmish_1.0.spec` has `codesign_identity=None`), so Gatekeeper/quarantine plus a
missing or restricted system Perl kills it.

The decision was to remove the problem categorically rather than fix code signing:
rebuild as a static, client-side web app with **no ExifTool, no Perl, no per-OS
binary**, hosted on AlterVista as plain static files.

The original architecture plan is at
`~/.claude/plans/vast-dreaming-stallman.md`. It is still the reference for scope,
risk assessment and phase definitions. Read §7 (phases) and §8 (risks) before
planning further work. Two of its decisions have since changed — see §3 below.

---

## 2. What is done

Phases 0 through 4 of the plan. Concretely:

**ExifTool is gone.** `src/core/flir.ts` parses the FLIR APP1 blocks directly.
The format was reverse-engineered against the sample files and every field was
confirmed by matching it to ExifTool's own reported values. Layout as verified:

- JPEG APP1 segments whose payload starts with `FLIR\0` carry an **8-byte header**;
  byte 6 is the chunk index, byte 7 the chunk count minus one. Concatenating the
  chunks in index order yields an FFF container.
  (Note: 8 bytes, not the 7 you would guess from ExifTool's `x5CC` unpack.)
- FFF header: magic `FFF\0`; index offset at `0x18` and entry count at `0x1c`,
  both **big-endian**.
- Index entries are 32 bytes, **big-endian**: mainType u16, subType u16, version u32,
  indexID u32, dataOffset u32, dataLength u32. Unused slots are zero-filled and
  trailing slots contain garbage — filter on `mainType != 0` and a bounds check.
- Record payloads are **little-endian**. Records used: `1` RawData,
  `14` EmbeddedImage (visible JPEG), `32` CameraInfo, `42` ImageInfo
  (`Real2IR` float32 @ 0x00, then int16 `OffsetX`, `OffsetY`, `PiPX1`, `PiPX2`,
  `PiPY1`, `PiPY2` — only the first three are read).
- Image records (1 and 14) have a `0x20`-byte header: width at offset 2, height at 4
  (u16 LE), pixel data from `0x20`.
- CameraInfo field offsets, each confirmed against ExifTool output:
  `0x20` Emissivity, `0x24` ObjectDistance, `0x28` ReflectedApparentTemperature (K),
  `0x2c` AtmosphericTemperature (K), `0x30` IRWindowTemperature (K),
  `0x34` IRWindowTransmission, `0x3c` RelativeHumidity (fraction),
  `0x58` PlanckR1, `0x5c` PlanckB, `0x60` PlanckF,
  `0x70`–`0x80` AtmosphericTrans alpha1/alpha2/beta1/beta2/X,
  `0x308` PlanckO (**int32**, not float), `0x30c` PlanckR2.

**16-bit PNG decoding is hand-rolled** (`src/core/png16.ts`). This is not
gold-plating: the browser's native image decoder routes through an 8-bit canvas and
would silently destroy radiometric precision. Only the case FLIR uses is supported
(16-bit grayscale, non-interlaced); `unzlibSync` from `fflate` does the inflate.
FLIR stores samples little-endian inside a spec-big-endian PNG, so a spec-compliant
decode must be byte-swapped — the desktop app does the same via numpy's `byteswap`.

**Planck inversion** (`src/core/planck.ts`) is a direct translation of
`_calculate_temperatures_from_raw` and `_apply_environmental_correction`.

**36 palettes** are precomputed offline by `tools/generate_palettes.py` into
`src/core/palettes.json` (base64 256×3 LUTs). matplotlib is a build-time dependency
only. Sampling at bin centres `(i + 0.5) / 256` reproduces matplotlib's
`int(x * N)` indexing exactly — the test proves this byte-for-byte.

**UI** (`src/App.svelte`, `src/lib/Viewer.svelte`): open via picker or drag-drop,
palette selection + inversion, auto/manual temperature range, editable thermal
parameters, pan/zoom canvas, per-pixel temperature probe, visible-image overlay with
all 13 Qt blend modes **and the desktop's manual alignment** (scale, offsets,
opacity), colour-bar legend, PNG and visible-JPEG export.

**Visible-photo filters** (`src/core/imageFilter.ts`): 20 post-processing filters
applied to the embedded visible frame *before* it is composited under the thermal
layer — never to radiometric data. A fast path hands Canvas2D a `filter` string
(grayscale, bw, sepia, invert, contrast, vivid, warm, cool, blur); a pixel path
walks an ImageData buffer (sharpen, edges/Sobel, emboss, threshold, posterize,
halftone, ordered dither, duotone, histogram equalize, pixelate, vignette). The
module is DOM-free (via `render.ts`'s canvas helpers) so the batch worker runs it
too; it is *not* imported by `render.ts` — `App.svelte` and `pipeline.ts` filter
the visible image and hand the result to `composite`, keeping `render.ts` pure
geometry. Each filter has one 0–100 strength slider mapped to its natural
parameter. Persisted in the sidecar under `visible_filter` `{ name, strength }`,
a web-only key the desktop ignores. The exported `_visible.jpg` stays the
untouched original; only the overlay reflects the filter.

The overlay's initial scale and offsets are derived from the FLIR ImageInfo record
(type 42): `scale = 1 / Real2IR`, `offsetX/Y = OffsetX/OffsetY` (visible-image
pixels), mirroring the desktop's `get_overlay_parameters_from_metadata`.
`alignmentFromMetadata()` in `render.ts` is the single source; "Reimposta
allineamento" returns to it. `tests/phase0.ts` checks these against the desktop
engine's own output for every sample.

**ROI system** (`src/core/roi.ts`, `src/core/roiRender.ts`, the ROI layer inside
`Viewer.svelte`): rectangles, spots and polygons, drawn and edited directly on the
canvas — move, corner resize, vertex editing, selection, delete. Masks and
statistics are a faithful port of `_create_roi_mask` and `compute_roi_temperatures`,
including Python's `int()` truncation and per-ROI emissivity. Statistics are shown
per ROI and burnt into labels exactly as `ui/roi_items.py` composes them.

Qt dispatched pointer events through its scene graph; there is none here, so
`Viewer.svelte` owns a single explicit state machine — what the pointer grabbed on
press decides what the drag means. That is the whole of the 1,516-line
`roi_items.py` translation, and it is the part to read first when changing
interaction.

**Session sidecars** (`src/core/session.ts`): the desktop's own JSON schema,
unchanged, so a `<image>.json` opens in either app. Saving is an explicit download
and resuming means opening the JSON alongside the image — see §4.2 of the plan and
the note below.

**Batch** (`src/lib/batch.worker.ts`, `src/core/pipeline.ts`): many files through a
Web Worker, each producing the same output set as the desktop's
`_export_image_analysis` (`_thermal.png`, `_thermal_with_rois.png`, `_visible.jpg`,
`_overlay.png`, `_data.csv`) plus a session sidecar, packaged into one zip with
`fflate`. `pipeline.ts` is shared with the interactive export buttons so the two
paths cannot drift. The worker is also why `render.ts` abstracts over
`HTMLCanvasElement` / `OffscreenCanvas`: there is no `document` inside a worker.

Build output: ~310 kB JS (116 kB gzip) plus a 74 kB worker chunk. Leaflet (the
map view, below) is most of the growth from the pre-map ~124 kB.

**Map view** (`src/lib/MapView.svelte`, `parseGps()` in `src/core/exif.ts`).
`parseGps` is a second, focused pass over the same Exif TIFF that `parseExif`
walks: IFD0 → GPSInfo pointer → lat/lon (deg/min/sec rationals + N/S/E/W ref),
altitude (+ `GPSAltitudeRef`), `GPSImgDirection` (+ ref). It returns plain
numbers; `parseExif` still produces the display strings for the EXIF modal. The
"Mappa" toggle in `App.svelte` (keyboard `M`) swaps the thermal canvas for a
Leaflet map without unmounting `Viewer`, so pan/zoom survives. Points: the whole
folder when one is open (scanned lazily on first open, reading only the first
256 kB of each file — the Exif APP1 sits at the head, before the bulky FLIR
blocks), otherwise the single open image. A marker carries a heading cone when
`GPSImgDirection` is present; its popup opens that frame back in the viewer.

FLIR cameras routinely write one coarse fix (~4 decimals ≈ 11 m) for a whole
session, so markers are clustered by **on-screen** distance, recomputed on
`zoomend`: overlapping pins merge into a counter that lists its shots in the
popup and splits again as you zoom in. A set at one identical coordinate never
splits — the list popup is the only way to reach those, by design.

**Geotag tool** (`public/geotag/`, self-contained HTML + vendored Leaflet /
piexifjs / fflate). For photos whose GPS is missing or session-cached: place them
on a map by hand, rewrite the standard EXIF GPS IFD (lat/lon via piexifjs, plus
optional `GPSImgDirection` true-north and `GPSAltitude`) into a downloaded ZIP.
The FLIR APP1's own duplicate GPS is **not** rewritten (harder, and Warmish reads
the standard IFD anyway). Vite copies `public/` into `dist/`, so it deploys as
`dist/geotag/`. The app links to `geotag/index.html` — **not** `geotag/`, which
the dev server SPA-falls-back to the app itself. `test:ui` drives it end to end:
launch from the sidebar link → load samples → place → export → assert the GPS
moved and `parseThermalImage` gives byte-identical raw/Planck/range/visible.

This is the **only** network access anywhere in the app. Basemap tiles come from
Esri World Imagery or OpenStreetMap (switchable, remembered in `localStorage`),
so the viewed area is disclosed to that provider — nothing else. A dismissible
notice states this the first time. Decided with the user: tiles-on with the
notice, over a tile-less relative plot. `tests/gps.ts` checks `parseGps` against
ExifTool's `-n` output for every `exemple img/` file (5 of 6 carry a fix);
`test:ui` drives the map with tile requests stubbed offline.

### Verification actually performed

`npm test` (`tests/phase0.ts`) — the Phase-0 gate. On first run it generates ground
truth by driving the **real** `core/thermal_engine.py` through
`tests/python_reference.py` (offscreen Qt + ExifTool + numpy), so the comparison is
against the shipping desktop implementation, not a reimplementation. For every
file in `exemple img/`, all green:

- raw sensor array identical (checksum) and dimensions identical
- PlanckR1/R2/B/F/O, Emissivity, reflected and atmospheric temperature exact
- temperatures within **1e-6 °C** over ~500 sampled pixels per image, computed from
  the parameters this parser derived — no values borrowed from the reference
- palette output byte-identical to matplotlib across 5 palettes
- embedded visible JPEG extracted

`npx tsx tests/phase3.ts` — the ROI gate, built the same way: it drives the real
`core/roi_controller.py` over a fixture of deliberately awkward geometry (a
rectangle straddling the left edge, a spot clipped by the top edge, a polygon
running below the sensor, a rectangle entirely outside). For each ROI it compares
the mask pixel for pixel (count **and** index checksum, so a geometry error cannot
hide behind unchanged statistics) and min/max/mean/median/std to 1e-6 °C. It also
round-trips a real desktop sidecar through the session schema.

`npm run test:ui` — the browser gate. Launches real Chromium via Playwright against
the production build, loads a sample through the file input, asserts the canvas
paints a real thermal map, exercises the overlay and its alignment, **draws a ROI
with real mouse events**, saves the session, reloads the page, reopens image +
session and checks the statistics come back identical, then runs a batch and
verifies the zip contents. It **fails on any console error**. Screenshots land in
`tests/screenshots/`.

All three suites are cheap and should be run after any core change.

---

## 3. Where this deviates from the plan

**TypeScript instead of Rust→WASM.** No Rust toolchain was installed, and §0 of the
plan already concedes that every hard requirement (client-side, zero upload,
cross-OS) comes from running in the browser, not from WASM. Decided with the user.
The core is pure and DOM-free behind a narrow interface in `src/core/`, so a WASM
swap later touches nothing else. Performance has not been an issue at 640×480.

**Svelte 5 + Vite** as the plan recommended. Runes (`$state`/`$derived`), no stores.

Everything else follows the plan, including single-threaded execution (no
`SharedArrayBuffer`, so no cross-origin-isolation headers needed on AlterVista).

---

## 4. A real bug found in the desktop app

The desktop reads metadata through PyExifTool, which passes `-n` (numeric) by
default. So `RelativeHumidity` arrives as a **fraction** (`0.5`) and is fed straight
into a correction term written for percent:

```python
humidity_correction = (relative_humidity - 50.0) * 0.00002
```

Every desktop pixel therefore carries a fixed **−0.00099 °C** bias. The web app uses
percent — consistent with its own UI and with the desktop's own default of `50.0` —
and `tests/phase0.ts` subtracts the bias explicitly rather than hiding it (search
`desktopBias`). The magnitude is far below sensor accuracy, so nothing was "fixed"
in the desktop app; it is documented, not papered over.

Related trap, already hit once: do **not** round the parsed metadata. The camera
stores `24.9999938964844 °C` as float32; rounding it to `25.0` shifts results by up
to 0.1 °C on a low-emissivity scene (`flir_20250428T191100.jpg`, ε = 0.30). Full
precision is kept in the core and rounding happens only in the UI's number inputs
(`shown()` / `edit()` in `App.svelte`).

---

## 5. What remains

### Phase 5 — parallel-run validation

The only phase still open, and the one that never fully closes. Do not retire the
desktop app: run both until feature parity is proven on real work. `tests/phase0.ts`
auto-discovers every `.jpg` in `exemple img/`, so widening coverage is just dropping
more files in there and deleting `tests/reference/`.

### Known gaps against the desktop

Small and deliberate, listed so nobody rediscovers them as bugs:

- **No auto-save.** A browser cannot silently write a sidecar next to the image.
  Saving is a download; resuming is opening the `.json` together with the photo.
  This is a genuine UX regression and the UI says so rather than hiding it. The
  File System Access API would remove it, Chromium-only — plan §4.2.
- **ROI emissivity uses the current parameters.** The desktop recomputes a ROI from
  the file's *metadata* parameters, ignoring UI edits to reflected/atmospheric
  temperature (`compute_roi_temperatures` calls `get_thermal_parameters_from_metadata`).
  The web app uses the parameters actually on screen, which is what a user expects.
  With unmodified parameters the two agree exactly, which is what `phase3.ts` checks.
- **Humidity units on import.** Desktop sidecars store a fraction (§4). A value at or
  below 1.5 is read as a fraction, anything above as percent; new files are written
  as percent. `humidityToPercent()` in `session.ts`.
- **No preset file for batch, and one batch path.** The desktop loads a separate
  preset JSON; the web app has no batch presets and no standalone "series" panel.
  Picking several images at once (or dropping them, or picking a directory) opens
  the filmstrip; each image keeps its own calibration, edits ride on top per
  image, and "Applica a selezionate" is the one way to push palette / parameters /
  areas across a set — with a visible per-image preview, unlike a blind copy.
  "Esporta cartella (.zip)" then feeds the same worker every other export uses.

---

## 6. The open risk

Six sample files, from two camera models, are the only ground truth in the suite.
FLIR's APP1 format varies across models and firmware in ways that are only partly
documented even in ExifTool's own reverse-engineered `FLIR.pm`. Passing on these
does **not** prove the parser generalises.

Since then, 91 further images from a second T530 shoot were parsed and every
metadata field compared against ExifTool: all 91 clean. Two of them
(`IR_30-06-2026_0004.jpg`, `_0078.jpg`, the latter spanning −7 to 155 °C) now sit in
`exemple img/` as regression coverage. This widens firmware and scene coverage but
**not** model coverage — it is the same camera as `FLIR0135`/`FLIR0354`. Only two
camera models have ever been tested. This risk does not close; it is
mitigated by expanding the sample set and by keeping the desktop app (with real
ExifTool) available as a cross-check. Any new camera variant handled by the parser
must be added to `exemple img/` so the suite guards against regressions.

Verify `perl exiftool_bin -j -G <file>` at the repo root when investigating a new
file — it works locally and is the fastest way to get an authoritative answer about
what a field *should* contain.

---

## 7. Commands

```bash
cd warmish-web
npm install
npm run dev                  # local dev server
npm run build                # -> dist/, ready to upload
npm test                     # Phase-0 + Phase-3 numeric gates vs the desktop engine
npm run test:ui              # browser gate (add -- --headed to watch)
python3 tools/generate_palettes.py   # only when constants.py changes
```

`npm test` needs the repo's `venv` (PySide6 + numpy + pyexiftool) for the first run
of each reference file; after that `tests/reference/*.json` is cached and the suite
is pure Node. Both `tests/reference/` and `tests/screenshots/` are gitignored.
