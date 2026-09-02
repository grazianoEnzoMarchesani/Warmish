# Warmish Web

Static, client-side rewrite of Warmish. Runs in any modern browser on any OS,
with no upload and no server-side processing — and, critically, **no ExifTool
and no Perl**, which is what breaks the desktop build on other Macs.

The one exception to "nothing leaves the browser" is the optional map view, which
loads basemap tiles from an external provider — see [Map view](#map-view).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | FLIR APP1 parser + Planck inversion, validated against the desktop engine | done |
| 1 | Core hardening (palette LUTs, blend modes, deterministic output) | done |
| 2 | Minimal UI: open → colour map → pan/zoom → probe → export PNG | done |
| 3 | ROI system (rect/spot/polygon) + session JSON import/export | done |
| 4 | Batch processing in a Web Worker + zip export | done |
| 5 | Parallel-run validation against the desktop app | in progress |

Phase 5 is the one that does not close on its own: keep both apps available and
keep widening the sample set. See "Verified equivalence" below for what is
currently proven, and HANDOFF.md §6 for the risk that remains.

## Deviation from the original plan

The plan called for a Rust→WASM core. This is **TypeScript instead**: no Rust
toolchain was installed, and §0 of the plan already notes that every hard
requirement (client-side, zero upload, cross-OS) comes from running in the browser,
not from WASM. The core lives behind a narrow, pure interface (`src/core/`), so
swapping in a WASM implementation later touches nothing else.

## Layout

```
src/core/      pure logic, no DOM — parser, Planck math, palettes, compositing,
               ROI masks and statistics, session I/O, the export pipeline
src/lib/       canvas viewer (pan/zoom + interactive ROI layer), batch worker
src/App.svelte UI shell
tools/         build-time palette LUT generation from matplotlib
tests/         Phase-0/3 numeric gates + browser smoke test
```

## Commands

```bash
npm install
npm run dev      # local development
npm run build    # -> dist/, ready to upload
npm test         # Phase-0 + Phase-3 gates: compares against the desktop engine
npm run test:ui  # drives the built app in Chromium (add -- --headed to watch)
```

`npm test` generates its own ground truth on first run by driving the real
`core/thermal_engine.py` (ExifTool + numpy) over `exemple img/`, then checks that
the browser core reproduces it. Delete `tests/reference/` to regenerate.

Palettes are regenerated only when `constants.py` changes:
`python3 tools/generate_palettes.py`.

## Verified equivalence

For every sample image, against the desktop engine:

- raw sensor array identical (checksum match), dimensions identical
- Planck constants R1/R2/B/F/O exact
- temperatures within 1e-6 °C over 500 sampled pixels per image
- palette output byte-identical to matplotlib for 5 palettes

For the ROI layer, against the desktop's own `ROIController`:

- masks identical pixel for pixel (count and index checksum), including ROIs
  that straddle or fall entirely outside the sensor
- min/max/mean/median/std within 1e-6 °C, recomputed with each ROI's own emissivity
- a sidecar written by the desktop imports, and a round trip preserves it

Beyond the suite, all 91 images from a second T530 shoot were parsed and checked
field by field against ExifTool: every value matched.

### One deliberate divergence

The desktop app reads metadata through PyExifTool's `-n` mode, so it receives
`RelativeHumidity` as a fraction (`0.5`) and feeds it into a correction term
written for percent. Every desktop pixel therefore carries a fixed −0.00099 °C
bias. The web app uses percent — matching its own UI and the desktop's own
default of `50.0` — and `tests/phase0.ts` subtracts the bias explicitly rather
than hiding it. The magnitude is far below sensor accuracy, but the desktop app
has a real unit bug here.

## Map view

`src/core/exif.ts` `parseGps()` reads the standard GPS IFD (latitude/longitude,
altitude, `GPSImgDirection`) straight from the JPEG. The "Mappa" toggle in the
viewer (`src/lib/MapView.svelte`, keyboard `M`) plots every GPS-tagged frame —
the whole folder when one is open, otherwise the current image — on a Leaflet
map, with a heading cone where `GPSImgDirection` is present and a click-through
back to the thermal viewer. FLIR cameras often stamp one coarse fix on a whole
session, so overlapping markers cluster into a counter that lists its shots and
splits as you zoom in.

This is the **only** part of the app that touches the network: the basemap tiles
come from Esri World Imagery or OpenStreetMap, so the area on screen is revealed
to that provider. No image or coordinate is uploaded. The map view says so, once,
in a dismissible notice; opening it is the user's choice. `tests/gps.ts` checks
`parseGps` against ExifTool's numbers for `exemple img/`, and `test:ui` exercises
the map with tile requests stubbed offline.

### Geotag companion tool

`public/geotag/` is a standalone static page (its own HTML + vendored Leaflet,
piexifjs and fflate — no shared code with the app) for the case the map view
exposes: photos with a missing or session-cached GPS fix. It plots the photos on
a map by hand and rewrites the **standard EXIF GPS** (lat/lon, optional heading
and altitude) into a downloadable ZIP — the FLIR radiometric block is left
untouched, verified in `test:ui`. The app links to it (`geotag/index.html` — the
explicit file, since Vite's dev server SPA-falls-back `/geotag/` to the app) from
the sidebar and from the map view's empty / all-same-coordinate states. It ships
in `dist/geotag/` via Vite's `public/` copy. See `public/geotag/README.md`.

## Deployment (AlterVista)

`npm run build`, then upload the **contents** of `dist/` to `public_html`
(or a subfolder — asset URLs are relative). `dist/.htaccess` sets MIME types,
compression, and cache headers. No PHP is involved in any processing path.
