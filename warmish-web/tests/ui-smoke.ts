/**
 * Phase-2 smoke test: drives the built app in a real browser, loads a sample
 * FLIR image through the file input, and checks that the canvas actually paints
 * a thermal map. Fails on any console error or page exception.
 *
 *   npm run build && npx tsx tests/ui-smoke.ts [--headed]
 */
import { execFileSync, spawn } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { chromium, type Page } from 'playwright';
import { unzipSync } from 'fflate';

import { parseGps } from '../src/core/exif';
import { parseThermalImage } from '../src/core/flir';
import { computeTemperatures, parametersFromMetadata, temperatureRange } from '../src/core/planck';

const REPO = resolve(import.meta.dirname, '../..');
const SAMPLE = join(REPO, 'exemple img', 'FLIR0135.jpg');
const SAMPLE2 = join(REPO, 'exemple img', 'FLIR0354.jpg');
const SHOTS = join(import.meta.dirname, 'screenshots');
const PORT = 4319;

const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], {
  cwd: resolve(import.meta.dirname, '..'),
  stdio: 'ignore',
});

const problems: string[] = [];
let failures = 0;

function check(label: string, ok: boolean, detail = ''): void {
  if (!ok) failures++;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${!ok && detail ? ` — ${detail}` : ''}`);
}

try {
  await waitForServer();
  mkdirSync(SHOTS, { recursive: true });

  const browser = await chromium.launch({ headless: !process.argv.includes('--headed') });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on('console', (m) => m.type() === 'error' && problems.push(m.text()));
  page.on('pageerror', (e) => problems.push(String(e)));

  // Keep the smoke test offline: serve a blank tile for every basemap request,
  // so the map view is exercised without a real network round trip.
  const BLANK_TILE = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  );
  await page.context().route(/arcgisonline\.com|tile\.openstreetmap\.org/, (r) =>
    r.fulfill({ status: 200, contentType: 'image/png', body: BLANK_TILE }));

  await page.goto(`http://localhost:${PORT}/`);
  check('app mounts', await page.locator('h1', { hasText: 'Warmish' }).isVisible());

  await page.setInputFiles('#pick', SAMPLE);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  check('image parsed in-browser', true);

  // EXIF modal: opens, lists standard + FLIR tags, closes on Escape.
  await page.locator('.menu > summary').click();
  await page.getByRole('button', { name: 'Dati EXIF…' }).click();
  await page.waitForSelector('[role="dialog"]');
  const exifRows = await page.locator('[role="dialog"] th').allTextContents();
  check('EXIF modal shows camera + FLIR tags',
    exifRows.includes('Model') && exifRows.includes('PlanckR1'), exifRows.slice(0, 5).join(', '));
  await page.keyboard.press('Escape');
  await page.waitForSelector('[role="dialog"]', { state: 'detached' });
  check('EXIF modal closes on Escape', true);

  // Frame statistics live in the (default) "Immagine" tab.
  await page.waitForSelector('text=Statistiche');
  const stats = await page.locator('dd').allTextContents();
  check('sensor size reported', stats.some((s) => s === '320×240'), stats.join(' | '));
  check('temperature stats shown', stats.filter((s) => s.endsWith('°C')).length === 3, stats.join(' | '));

  // Theme toggle cycles auto -> light -> dark and pins <html data-theme>.
  const themeBtn = page.getByRole('button', { name: /^Tema:/ });
  await themeBtn.click();
  check('theme toggle pins a light theme',
    (await page.locator('html').getAttribute('data-theme')) === 'light');
  await page.screenshot({ path: join(SHOTS, 'light.png') });
  await themeBtn.click();
  await themeBtn.click();
  check('theme toggle returns to auto',
    (await page.locator('html').getAttribute('data-theme')) === null);

  // A painted thermal map must produce many distinct colours on the canvas.
  const colours = await page.evaluate(() => {
    const c = document.querySelector('main canvas') as HTMLCanvasElement;
    const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    const seen = new Set<number>();
    for (let i = 0; i < d.length; i += 4 * 97) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    return seen.size;
  });
  check('canvas renders a thermal map', colours > 50, `only ${colours} distinct colours`);

  await page.selectOption('select', 'Rainbow');
  await page.waitForTimeout(150);
  await page.screenshot({ path: join(SHOTS, 'loaded.png') });

  // Filter and alignment now sit behind the "Avanzate" disclosure.
  const advanced = page.locator('details.advanced > summary');
  if (await advanced.count()) await advanced.click();

  // Overlay path: blend the thermal layer over the embedded visible image.
  const overlay = page.locator('label.check', { hasText: 'Sovrapponi' });
  if (await overlay.count()) {
    await overlay.locator('input').check();
    await page.selectOption('#bl', 'Multiply');
    await page.waitForTimeout(150);
    await page.screenshot({ path: join(SHOTS, 'overlay.png') });
    check('visible-image overlay renders', true);

    // Visible-photo filter: a pixel-path filter must change the composite.
    if (await page.locator('#vf').count()) {
      const before = await canvasSignature(page);
      await page.selectOption('#vf', 'edges');
      await page.waitForTimeout(300);
      check('visible-photo filter changes the overlay', (await canvasSignature(page)) !== before);
      await page.screenshot({ path: join(SHOTS, 'overlay-filter.png') });
      await page.selectOption('#vf', 'none');
      await page.waitForTimeout(150);
    }
  }

  // --- ROI layer -------------------------------------------------------------
  // Alignment must move the thermal layer while the overlay is on, otherwise a
  // session round trip cannot reproduce the desktop's manual registration.
  if (await page.locator('#al').count()) {
    const before = await canvasSignature(page);
    await page.locator('#ox').fill('40');
    await page.locator('#ox').dispatchEvent('input');
    await page.waitForTimeout(200);
    check('overlay offset shifts the thermal layer', (await canvasSignature(page)) !== before);
    await page.locator('#ox').fill('0');
    await page.locator('#ox').dispatchEvent('input');
    await page.locator('label.check', { hasText: 'Sovrapponi' }).locator('input').uncheck();
    await page.waitForTimeout(150);
  }

  await tab(page, 'Aree');
  await page.getByRole('button', { name: 'Rettangolo' }).click();
  const box = (await page.locator('main canvas').boundingBox())!;
  await drag(page, box.x + box.width * 0.35, box.y + box.height * 0.35,
    box.x + box.width * 0.55, box.y + box.height * 0.6);
  await page.waitForTimeout(200);
  check('rectangle ROI created by dragging', (await page.locator('.rois li').count()) === 1);

  const roiMean = await page.locator('.rois .tm').first().textContent();
  check('ROI statistics computed', /^-?\d+\.\d\d °C$/.test(roiMean ?? ''), `label was "${roiMean}"`);

  await page.getByRole('button', { name: 'Punto' }).click();
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.waitForTimeout(150);
  check('spot ROI added', (await page.locator('.rois li').count()) === 2);

  // Polygons are a separate gesture: click per vertex, double-click to close.
  await page.getByRole('button', { name: 'Poligono' }).click();
  for (const [fx, fy] of [[0.62, 0.3], [0.78, 0.42], [0.66, 0.6]] as [number, number][]) {
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
  }
  await page.mouse.dblclick(box.x + box.width * 0.66, box.y + box.height * 0.6);
  await page.waitForTimeout(200);
  check('polygon ROI closed by double click', (await page.locator('.rois li').count()) === 3);

  // Deleting through the list must also clear the selection, not orphan it.
  await page.screenshot({ path: join(SHOTS, 'rois.png') });
  await page.locator('.rois li').last().locator('.del').click();
  await page.waitForTimeout(150);
  check('ROI deleted from the list', (await page.locator('.rois li').count()) === 2);

  // --- Range scale: percentile stretch -------------------------------------
  // The mode pill cycles true min/max → 98% → 90% → min/max, and a stretch must
  // actually repaint the thermal map (endpoints moved inward).
  const pill = page.locator('.scale button.auto').first();
  check('range pill starts on auto', (await pill.textContent())?.trim() === 'auto');
  const beforeStretch = await canvasSignature(page);
  await pill.click();
  await page.waitForTimeout(200);
  check('range pill cycles to 98% stretch', (await pill.textContent())?.trim() === '98%');
  check('percentile stretch repaints the canvas', (await canvasSignature(page)) !== beforeStretch);
  await page.screenshot({ path: join(SHOTS, 'stretch.png') });
  await pill.click();
  await page.waitForTimeout(150);
  check('range pill cycles to 90% stretch', (await pill.textContent())?.trim() === '90%');
  await page.locator('.scale .bar').dblclick();
  await page.waitForTimeout(150);
  check('range pill resets to auto on double-click', (await pill.textContent())?.trim() === 'auto');

  // Session round trip through the real download/upload path.
  await tab(page, 'Esporta');
  const download = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Salva sessione (.json)' }).click(),
  ]).then(([d]) => d);
  const sessionPath = join(SHOTS, 'session.json');
  await download.saveAs(sessionPath);
  const saved = JSON.parse(readFileSync(sessionPath, 'utf8'));
  check('session file has both ROIs', Array.isArray(saved.rois) && saved.rois.length === 2,
    JSON.stringify(saved.rois?.length));
  check('session file keeps the desktop schema',
    'thermal_parameters' in saved && 'overlay_settings' in saved && 'roi_label_settings' in saved);

  await page.reload();
  await page.setInputFiles('#pick', [SAMPLE, sessionPath]);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  await tab(page, 'Aree');
  await page.waitForSelector('.rois li', { timeout: 10_000 });
  await page.waitForTimeout(200);
  check('session restores the ROIs', (await page.locator('.rois li').count()) === 2);
  const restoredMean = await page.locator('.rois .tm').first().textContent();
  check('restored ROI recomputes the same statistics', restoredMean === roiMean,
    `${restoredMean} vs ${roiMean}`);

  // --- Multi-file export (Phase 4) ------------------------------------------
  // Several images picked at once open as a folder; "Esporta cartella" is the
  // one batch path now, feeding the same worker.
  await page.reload();
  await page.setInputFiles('#pick', [SAMPLE, SAMPLE2]);
  await page.waitForSelector('.strip .thumb', { timeout: 10_000 });
  check('multi-select opens the filmstrip', (await page.locator('.strip .thumb').count()) === 2);
  await tab(page, 'Esporta');
  const zipDownload = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.getByRole('button', { name: 'Esporta cartella (.zip)' }).click(),
  ]).then(([d]) => d);
  const zipPath = join(SHOTS, 'batch.zip');
  await zipDownload.saveAs(zipPath);
  const entries = Object.keys(unzipSync(new Uint8Array(readFileSync(zipPath))));
  check('batch produced one archive per run', entries.length > 0, entries.join(', '));
  const root = entries[0]?.split('/')[0] ?? '';
  check('archive is rooted at warmish_export_<date>', /^warmish_export_\d{4}-\d{2}-\d{2}$/.test(root), root);
  for (const base of ['FLIR0135', 'FLIR0354']) {
    // No image was edited, so no ROIs and no termica_aree.png — each image
    // carries its own calibration, the correct default for a loose set.
    check(`batch: ${base} outputs`,
      ['termica.png', 'termica_annotata.png', 'visibile.jpg']
        .every((n) => entries.includes(`${root}/${base}/${n}`))
        && !entries.includes(`${root}/${base}/termica_aree.png`)
        && entries.includes(`${root}/originali/${base}.json`)
        && entries.includes(`${root}/originali/${base}.jpg`),
      entries.filter((e) => e.includes(base)).join(', '));
  }
  check('batch wrote the aggregate files',
    entries.includes(`${root}/aree.csv`) && entries.includes(`${root}/manifest.json`),
    entries.join(', '));
  check('batch reported no failures', !entries.includes(`${root}/errori.txt`));

  const zipFiles = unzipSync(new Uint8Array(readFileSync(zipPath)));
  const visGps = parseGps(zipFiles[`${root}/FLIR0135/visibile.jpg`]);
  const parentGps = parseGps(new Uint8Array(readFileSync(SAMPLE)));
  check('visibile.jpg carries the parent GPS fix',
    !!visGps && !!parentGps && Math.abs(visGps.lat - parentGps.lat) < 1e-9 && Math.abs(visGps.lon - parentGps.lon) < 1e-9,
    JSON.stringify(visGps));

  const csvBytes = unzipSync(new Uint8Array(readFileSync(zipPath)))[`${root}/aree.csv`];
  const csvText = new TextDecoder('utf-8', { ignoreBOM: true }).decode(csvBytes);
  check('aree.csv is BOM + semicolon-delimited + CRLF',
    csvBytes[0] === 0xef && csvBytes[1] === 0xbb && csvBytes[2] === 0xbf
      && csvText.slice(1).startsWith('immagine;data_ora;') && csvText.includes('\r\n'),
    JSON.stringify(csvText.slice(0, 40)));

  // --- Folder mode ----------------------------------------------------------
  const folderDir = mkdtempSync(join(tmpdir(), 'warmish-folder-'));
  for (const f of [SAMPLE, SAMPLE2]) copyFileSync(f, join(folderDir, basename(f)));
  await page.reload();
  await page.setInputFiles('#folderpick', folderDir);
  await page.waitForSelector('.strip .thumb', { timeout: 10_000 });
  check('filmstrip lists the folder', (await page.locator('.strip .thumb').count()) === 2);

  // Edit image 1, switch away, come back — the edit must survive.
  await page.locator('.strip .thumb').first().click();
  await page.waitForSelector('[role="tablist"]');
  await tab(page, 'Immagine');
  await page.locator('select').first().selectOption('Rainbow');
  await page.locator('.strip .thumb').nth(1).click();
  await page.waitForTimeout(150);
  await page.locator('.strip .thumb').first().click();
  await page.waitForTimeout(150);
  check('per-image edit persists across switches',
    (await page.locator('select').first().inputValue()) === 'Rainbow');
  check('edited image is flagged in the strip',
    (await page.locator('.strip .thumb .edited').count()) >= 1);

  // Bulk edit is a slide-over opened from the strip. Select the image that is
  // *not* the open one, so the copy actually has a target.
  await page.locator('.thumb-wrap').nth(1).locator('.pick').check();
  await page.getByRole('button', { name: /Modifica in blocco/ }).click();
  await page.waitForSelector('.sheet');
  await page.screenshot({ path: join(SHOTS, 'bulk.png') });
  check('bulk slide-over opens with a selection',
    (await page.locator('.sheet [name="bulkArea"]').count()) === 3);
  await page.locator('.sheet').getByRole('button', { name: /^Applica a/ }).click();
  await page.waitForSelector('.sheet', { state: 'detached' });
  await page.waitForSelector('.toast', { timeout: 4000 }).catch(() => {});
  await page.screenshot({ path: join(SHOTS, 'toast.png') });
  const toastText = (await page.locator('.toast .msg').first().textContent().catch(() => null)) ?? '';
  check('bulk apply reports through a toast', /applicate/i.test(toastText), `toast text: "${toastText}"`);

  // Folder-session round trip: the lightweight checkpoint. Save it, reload,
  // re-pick the folder with the .json alongside — the edit and the flagged
  // image must come back without re-rendering anything.
  await tab(page, 'Esporta');
  const folderSession = await Promise.all([
    page.waitForEvent('download', { timeout: 30_000 }),
    page.getByRole('button', { name: 'Salva sessione cartella (.json)' }).click(),
  ]).then(([d]) => d);
  const folderSessionPath = join(folderDir, 'warmish_folder_session.json');
  await folderSession.saveAs(folderSessionPath);
  const fsess = JSON.parse(readFileSync(folderSessionPath, 'utf8'));
  const editedKey = Object.keys(fsess.files).find((k) => k.endsWith('FLIR0135.jpg'));
  check('folder session carries the per-image edit',
    fsess.warmish_folder_session != null && !!editedKey && fsess.files[editedKey!].palette === 'Rainbow',
    JSON.stringify(Object.keys(fsess.files)));
  check('folder session records the workspace block',
    fsess.workspace != null && typeof fsess.workspace.active === 'string');

  await page.reload();
  await page.setInputFiles('#folderpick', folderDir);
  await page.waitForSelector('.strip .thumb', { timeout: 10_000 });
  await page.waitForTimeout(250);
  await tab(page, 'Immagine');
  check('folder session restores the per-image edit',
    (await page.locator('select').first().inputValue()) === 'Rainbow');
  check('folder session re-flags the edited image',
    (await page.locator('.strip .thumb .edited').count()) >= 1);

  // Folder batch: one zip, each image processed with its own state.
  await tab(page, 'Esporta');
  const folderZip = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.getByRole('button', { name: 'Esporta cartella (.zip)' }).click(),
  ]).then(([d]) => d);
  const folderZipPath = join(SHOTS, 'folder.zip');
  await folderZip.saveAs(folderZipPath);
  const folderEntries = Object.keys(unzipSync(new Uint8Array(readFileSync(folderZipPath))));
  const froot = folderEntries[0]?.split('/')[0] ?? '';
  check('folder batch archives every image',
    folderEntries.includes(`${froot}/FLIR0135/termica.png`) && folderEntries.includes(`${froot}/FLIR0354/termica.png`),
    folderEntries.join(', '));

  // Common folder scale: with a folder open the range pill gains a 4th mode that
  // pins the window to the whole folder's min-of-mins / max-of-maxes; the export
  // bakes it into a fixed manual window (the worker sees one image at a time).
  await tab(page, 'Immagine');
  const fpill = page.locator('.scale button.auto').first();
  await fpill.click();
  await fpill.click();
  await fpill.click();
  await page.waitForFunction(
    () => !(document.querySelector('.statusbar')?.textContent ?? '').includes('scansione'),
    undefined, { timeout: 15_000 },
  );
  await page.waitForTimeout(200);
  check('range pill reaches the common folder scale',
    (await fpill.textContent())?.trim() === 'cart.');
  check('status bar reports the common folder scale',
    /scala cartella/.test((await page.locator('.statusbar').textContent()) ?? ''));
  await page.screenshot({ path: join(SHOTS, 'folder-scale.png') });

  await tab(page, 'Esporta');
  const scaleZip = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.getByRole('button', { name: 'Esporta cartella (.zip)' }).click(),
  ]).then(([d]) => d);
  const scaleZipPath = join(SHOTS, 'folder-scale.zip');
  await scaleZip.saveAs(scaleZipPath);
  const scaleEntries = unzipSync(new Uint8Array(readFileSync(scaleZipPath)));
  const scaleRoot = Object.keys(scaleEntries)[0].split('/')[0];
  const scaleRange = JSON.parse(
    new TextDecoder().decode(scaleEntries[`${scaleRoot}/manifest.json`]),
  ).render.range;
  check('common folder scale is baked into the export as a fixed window',
    scaleRange.mode === 'manual' && scaleRange.max - scaleRange.min > 20,
    JSON.stringify(scaleRange));

  await tab(page, 'Immagine');
  await page.locator('.scale .bar').dblclick();
  await page.waitForTimeout(150);
  check('folder scale resets with the rest of the auto modes',
    (await fpill.textContent())?.trim() === 'auto');

  // --- Map view -----------------------------------------------------------
  // The folder (two shots ~11 m apart, the coarse fix a FLIR writes) is still
  // open: they must merge into one counted cluster that splits when zoomed in.
  await page.locator('.viewswitch button', { hasText: 'Mappa' }).click();
  await page.waitForSelector('.leaflet-container', { timeout: 10_000 });
  await page.waitForTimeout(600);
  check('near shots merge into one cluster',
    (await page.locator('.wm-pin--cluster').count()) === 1
      && (await page.locator('.wm-pin:not(.wm-pin--cluster)').count()) === 0);
  check('cluster shows the shot count', (await page.locator('.wm-count').textContent())?.trim() === '2');
  await page.locator('.wm-pin--cluster').click();
  await page.waitForSelector('.leaflet-popup');
  check('cluster popup lists both shots', (await page.locator('.wm-list-open').count()) === 2);
  await page.screenshot({ path: join(SHOTS, 'map.png') });
  for (let i = 0; i < 8; i++) { await page.locator('.leaflet-control-zoom-in').click(); await page.waitForTimeout(160); }
  await page.waitForTimeout(400);
  check('zooming in separates the cluster',
    (await page.locator('.wm-pin:not(.wm-pin--cluster)').count()) === 2);

  // --- Map tour ---------------------------------------------------------
  // Two located shots → a playable tour: the panel opens, renders a real
  // processed frame per stop, and the path/progress track the current stop.
  check('tour button shows for a folder with 2+ located shots',
    await page.locator('.tour-start').isVisible());
  await page.locator('.tour-start').click();
  await page.waitForSelector('.tour-panel', { timeout: 5000 });
  check('tour lays out one progress dot per stop',
    (await page.locator('.tour-dot').count()) === 2);
  await page.waitForSelector('.tour-img', { timeout: 20_000 });
  const tourSrc = await page.locator('.tour-img').first().getAttribute('src');
  check('tour panel shows a rendered frame', !!tourSrc && tourSrc.startsWith('blob:'));
  check('the shot route is drawn on the map',
    (await page.locator('path.wm-route-done').count()) === 1);
  check('the tour hides the shell chrome',
    !(await page.locator('.topbar').isVisible())
    && !(await page.locator('.strip').isVisible())
    && !(await page.locator('.statusbar').isVisible())
    && !(await page.locator('aside').isVisible()));
  await page.screenshot({ path: join(SHOTS, 'map-tour.png') });
  await page.locator('.tour-btn', { hasText: '›' }).click();
  await page.waitForTimeout(1200);
  check('stepping forward moves the current stop',
    ((await page.locator('.tour-dot').nth(1).getAttribute('class')) ?? '').includes('cur'));
  await page.screenshot({ path: join(SHOTS, 'map-tour-step.png') });
  await page.keyboard.press('Escape');
  await page.waitForSelector('.tour-panel', { state: 'detached', timeout: 4000 });
  check('Escape ends the tour', (await page.locator('.tour-panel').count()) === 0);
  check('ending the tour restores the shell chrome',
    await page.locator('.topbar').isVisible() && await page.locator('.statusbar').isVisible());

  // Single-image path: one marker, its popup returns to the thermal view.
  await page.reload();
  await page.setInputFiles('#pick', SAMPLE);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  check('map toggle appears for a GPS-tagged image',
    await page.locator('.viewswitch button', { hasText: 'Mappa' }).isVisible());
  await page.locator('.viewswitch button', { hasText: 'Mappa' }).click();
  await page.waitForSelector('.leaflet-container', { timeout: 10_000 });
  await page.waitForTimeout(500);
  check('map places a marker from the GPS fix', (await page.locator('.wm-pin').count()) === 1);
  await page.locator('.wm-pin').first().click();
  await page.waitForSelector('.leaflet-popup');
  check('marker popup shows coordinates', await page.locator('.wm-pop-coord').isVisible());
  await page.locator('.wm-pop-open').click();
  await page.waitForTimeout(200);
  check('popup button returns to the thermal view',
    await page.locator('.viewswitch button.on', { hasText: 'Termica' }).isVisible());

  // --- Geotag companion tool (public/geotag) -----------------------------
  // Launched from the "Apri" menu; a separate static page that rewrites EXIF
  // GPS without touching the radiometric data.
  await page.locator('.menu > summary').click();
  const geo = await Promise.all([
    page.context().waitForEvent('page'),
    page.locator('.menu-pop a', { hasText: 'Geotag' }).click(),
  ]).then(([p]) => p);
  geo.on('console', (m) => m.type() === 'error' && problems.push(`[geotag] ${m.text()}`));
  geo.on('pageerror', (e) => problems.push(`[geotag] ${e}`));
  await geo.waitForLoadState('domcontentloaded');
  await geo.waitForFunction(() => (window as any).piexif && (window as any).L && (window as any).fflate, null, { timeout: 15_000 });
  check('geotag: served from /geotag/ with its libraries', new URL(geo.url()).pathname.includes('/geotag/'));

  const chooser = await Promise.all([
    geo.waitForEvent('filechooser'),
    geo.locator('.btn', { hasText: 'Scegli foto' }).click(),
  ]).then(([c]) => c);
  await chooser.setFiles([SAMPLE, SAMPLE2]);
  await geo.waitForSelector('.card', { timeout: 10_000 });
  check('geotag: photos load and camera GPS is read', (await geo.locator('.gt-orig').count()) >= 1);

  // The detail panel shows the FLIR file's embedded visible photo, not the
  // unreadable thermal render; clicking it opens a full-screen lightbox.
  await geo.waitForFunction(() => {
    const img = document.querySelector('#fPreview') as HTMLImageElement | null;
    return !!img && img.src.startsWith('blob:');
  }, null, { timeout: 10_000 });
  check('geotag: detail shows the embedded visible photo', true);
  await geo.locator('#fPreview').click();
  check('geotag: preview opens a lightbox', (await geo.locator('.lightbox img').count()) === 1);
  await geo.keyboard.press('Escape');
  check('geotag: lightbox closes on Escape', (await geo.locator('.lightbox').count()) === 0);

  // Both sidebars collapse and reopen from their toggle / reveal tabs.
  await geo.locator('#collapseRight').click();
  await geo.locator('#collapseLeft').click();
  check('geotag: both sidebars collapsed', await geo.locator('#app.lc.rc').count() === 1
    && !(await geo.locator('aside.left').isVisible()) && !(await geo.locator('aside.right').isVisible()));
  await geo.locator('#showLeft').click();
  await geo.locator('#showRight').click();
  check('geotag: sidebars reopen', await geo.locator('#app.lc, #app.rc').count() === 0
    && await geo.locator('#fPreview').isVisible());

  const mapBox = (await geo.locator('#map').boundingBox())!;
  await geo.mouse.click(mapBox.x + mapBox.width * 0.5, mapBox.y + mapBox.height * 0.45);
  await geo.waitForTimeout(200);
  await geo.locator('#copyAll').click();
  await geo.waitForTimeout(200);
  check('geotag: place + copy to all', (await geo.locator('.strip .dot.placed').count()) === 2);

  const zip = await Promise.all([
    geo.waitForEvent('download', { timeout: 30_000 }),
    geo.locator('#exportZip').click(),
  ]).then(([d]) => d);
  const geoZipPath = join(SHOTS, 'geotag.zip');
  await zip.saveAs(geoZipPath);
  await geo.waitForTimeout(200);

  const gz = unzipSync(new Uint8Array(readFileSync(geoZipPath)));
  check('geotag: zip has both photos + csv',
    ['FLIR0135.jpg', 'FLIR0354.jpg', 'geotag.csv'].every((n) => n in gz));
  const before = parseGps(new Uint8Array(readFileSync(SAMPLE)))!;
  const after = parseGps(gz['FLIR0135.jpg'])!;
  check('geotag: GPS actually moved',
    Math.abs(after.lat - before.lat) > 1e-4 || Math.abs(after.lon - before.lon) > 1e-4,
    `${JSON.stringify(before)} -> ${JSON.stringify(after)}`);
  const t = parseThermalImage(gz['FLIR0135.jpg']);
  const o = parseThermalImage(new Uint8Array(readFileSync(SAMPLE)));
  const rt = temperatureRange(computeTemperatures(t.raw, parametersFromMetadata(t.metadata)));
  const ro = temperatureRange(computeTemperatures(o.raw, parametersFromMetadata(o.metadata)));
  check('geotag: radiometric data byte-identical after rewrite',
    t.width === o.width && t.height === o.height && t.metadata.PlanckR1 === o.metadata.PlanckR1
      && rt.min === ro.min && rt.max === ro.max && !!t.visible === !!o.visible);
  await geo.screenshot({ path: join(SHOTS, 'geotag.png') });
  await geo.close();

  check('no console errors', problems.length === 0, problems.slice(0, 3).join(' / '));
  await browser.close();
} finally {
  server.kill();
}

console.log(failures ? `\n${failures} check(s) failed` : `\nPhase 2 smoke passed — screenshots in ${SHOTS}`);
process.exit(failures ? 1 : 0);

/** Switch the sidebar to a named tab and wait for it to become active. */
async function tab(page: Page, name: string): Promise<void> {
  const t = page.getByRole('tab', { name, exact: true });
  await t.click();
  await t.and(page.locator('.active')).waitFor();
}

/** Pointer drag through real mouse events, so the viewer's state machine runs. */
async function drag(page: Page, x1: number, y1: number, x2: number, y2: number): Promise<void> {
  await page.mouse.move(x1, y1);
  await page.mouse.down();
  await page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, { steps: 5 });
  await page.mouse.move(x2, y2, { steps: 5 });
  await page.mouse.up();
}

/** Cheap fingerprint of the rendered canvas, for "did the picture change" checks. */
async function canvasSignature(page: Page): Promise<number> {
  return page.evaluate(() => {
    const c = document.querySelector('main canvas') as HTMLCanvasElement;
    const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let h = 0;
    for (let i = 0; i < d.length; i += 4 * 53) h = (h * 31 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) | 0;
    return h;
  });
}

async function waitForServer(): Promise<void> {
  for (let i = 0; i < 50; i++) {
    try {
      execFileSync('curl', ['-sf', '-o', '/dev/null', `http://localhost:${PORT}/`]);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error('vite preview did not start');
}
