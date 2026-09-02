# Warmish Web — output spec

Redesign degli output esterni. Sostituisce interamente il set precedente
(`_thermal.png`, `_thermal_with_rois.png`, `_visible.jpg`, `_overlay.png`,
`_data.csv` + sidecar sciolti). Concordato con l'utente 2026-09-02.

---

## Principio

Una immagine → un "set" di output. Il batch = N set identici + file aggregati.
L'export interattivo di una singola immagine produce **esattamente** lo stesso
set del batch per quella immagine — un solo percorso di codice (`pipeline.ts`),
zero export "speciali" lato UI.

Tutto esce in **un unico zip**.

---

## Struttura dello zip

```
warmish_export_<YYYY-MM-DD>/
  aree.csv                    CSV unico: tutti i ROI di tutte le immagini
  manifest.json               impostazioni, versione, parametri per-file, elenco scatti
  punti_scatto.geojson        se almeno un'immagine ha GPS
  errori.txt                  solo se qualche file fallisce
  originali/
    IR_0001.jpg               originale FLIR, invariato (GPS/data intatti)
    IR_0001.json              sessione: parametri + ROI + overlay + filtro
    ...
  IR_0001/
    termica.png               nativa 640×480, nessuna decorazione
    termica_annotata.png      4×, legenda in basso, senza ROI
    termica_aree.png          4×, legenda + ROI + label — solo se ci sono ROI
    sovrapposta.png           4×, legenda + ROI + label — solo se overlay attivo
    visibile.jpg              risoluzione originale, EXIF del padre innestato
  IR_0002/
    ...
```

Il `.json` di sessione sta **solo** in `originali/`, mai duplicato nelle
cartelle-immagine (che restano solo raster derivati).

Nome cartella-immagine = basename del file originale. Collisioni (multi-select da
cartelle diverse) → suffisso `_2`, `_3`.

---

## PNG per immagine

| file | quando | risoluzione | contenuto |
|---|---|---|---|
| `termica.png` | sempre | 640×480 nativi | solo immagine colorizzata, zero decorazioni |
| `termica_annotata.png` | sempre | 4× (2560×1920) | + legenda orizzontale in basso, **senza** ROI |
| `termica_aree.png` | se `rois.length > 0` | 4× | + legenda + ROI + label |
| `sovrapposta.png` | se overlay attivo | 4× | composito visibile+termico (scala, posizione, opacità, blend, filtro visibile) + legenda + ROI + label |

Il fattore 4× è una costante (`DECORATED_SCALE` in `pipeline.ts`), facile da
cambiare.

Render **deterministico**: nessuna dipendenza da zoom/pan/dimensione finestra.
`termica.png` è un render fisso a risoluzione sensore; gli altri a `4 ×` quella.

### Legenda

Nuova variante **orizzontale in basso** (oggi `drawLegend` la fa verticale a
destra). La barra colore del **viewer live resta verticale a destra** — non si
tocca.

Caveat noto (deciso di tenere la legenda comunque): sull'overlay con
`blend ≠ normal` o `opacity < 1` i colori a schermo non corrispondono più alla
LUT, quindi la scala è indicativa. La versione quantitativa affidabile è sempre
`termica_aree.png`.

---

## `visibile.jpg`

Il frame visibile estratto dal contenitore FFF ha solo un EXIF stub (niente GPS,
niente data). Si **innesta il segmento APP1/EXIF del JPEG padre** — gli stessi
byte che `parseExif`/`parseGps` leggono — *sostituendo* lo stub esistente
(`injectExifApp1` in `exif.ts`). Nessuna dipendenza nuova, nessun EXIF writer.

Il file resta l'originale non filtrato: il filtro visibile compare **solo** dentro
`sovrapposta.png`.

---

## `aree.csv`

Formato per **Excel italiano**: separatore `;`, decimale `,`, BOM UTF-8 in testa,
righe terminate `CRLF`.

Quoting: una cella che contiene `;`, `"`, CR o LF va tra virgolette con `"` → `""`.
Il decimale `,` non richiede quoting (il separatore è `;`).

Una riga = un ROI in una immagine. **Le immagini senza ROI non compaiono**
(sono comunque elencate in `manifest.json`).

| colonna | note |
|---|---|
| `immagine` | nome file originale, es. `IR_0001.jpg` |
| `data_ora` | `YYYY-MM-DD HH:MM:SS`, ora locale naive da DateTimeOriginal |
| `latitudine` | gradi decimali, ~6 decimali; vuoto se assente |
| `longitudine` | idem |
| `quota_m` | vuoto se assente |
| `direzione_deg` | GPSImgDirection; vuoto se assente |
| `roi` | nome ROI |
| `forma` | `Rettangolo` / `Punto` / `Poligono` |
| `geometria` | formato piatto (coord. pixel intere) — vedi sotto |
| `centro_x` | pixel, sempre valorizzato |
| `centro_y` | idem |
| `area_px` | numero di pixel nella maschera |
| `emissivita` | per-ROI, 3 decimali |
| `temp_riflessa_c` | parametro usato per questa ROI |
| `temp_atmosferica_c` | idem |
| `umidita_pct` | idem (percento) |
| `distanza_m` | ObjectDistance |
| `trasmittanza_atm` | trasmittanza atmosferica applicata |
| `min_c` | 4 decimali |
| `max_c` | idem |
| `media_c` | idem |
| `mediana_c` | idem |
| `dev_std_c` | idem |
| `pos_min_x` | pixel del minimo dentro la ROI |
| `pos_min_y` | idem |
| `pos_max_x` | pixel del massimo |
| `pos_max_y` | idem |
| `camera` | modello camera |
| `larghezza_px` | dimensione sensore |
| `altezza_px` | idem |

I parametri per-ROI in ogni riga rendono le statistiche **riproducibili**.

### `geometria`

- `RETT x=10 y=20 l=50 h=40`
- `PUNTO x=100 y=90 r=10`
- `POLIGONO 12 5 40 5 40 60 12 60` (coppie `x y` in sequenza)

---

## `manifest.json`

```json
{
  "warmish_version": "1.0.0",
  "exported_at": "2026-09-02T14:23:11+02:00",
  "image_count": 42,
  "csv_format": { "delimiter": ";", "decimal": ",", "encoding": "utf-8-bom", "newline": "crlf" },
  "render": {
    "palette": "inferno",
    "inverted": false,
    "range": { "mode": "auto" },
    "legend": true,
    "decorated_scale": 4,
    "overlay": { "blend": "normal", "opacity": 1, "alignment": { }, "visible_filter": { } },
    "labels": { }
  },
  "parameters": null,
  "images": [
    {
      "file": "IR_0001.jpg",
      "folder": "IR_0001",
      "dimensions": [640, 480],
      "camera": "FLIR T530",
      "datetime": "2026-06-30 14:23:11",
      "gps": { "lat": 43.1, "lon": 13.0, "alt_m": 320, "direction_deg": 210 },
      "parameters": { "Emissivity": 0.95, "ReflectedApparentTemperature": 20.0 },
      "roi_count": 3,
      "outputs": ["termica.png", "termica_annotata.png", "termica_aree.png", "visibile.jpg"]
    }
  ]
}
```

- `range.mode`: `"auto"` oppure `{ "mode": "manual", "min": -7, "max": 155 }`
- `parameters` (livello alto): `null` = ogni immagine usa i propri; altrimenti
  l'oggetto override globale applicato a tutte
- `images[].gps`: `null` se il file non ha fix
- descrive il render aggregato dell'export; per riaprire il lavoro sulla cartella
  c'è il kit `originali/` (completo) o "Salva sessione cartella (.json)" (leggero)

---

## `punti_scatto.geojson`

`FeatureCollection` di `Point`, WGS84. Presente solo se almeno un'immagine ha GPS.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [13.0, 43.1, 320] },
      "properties": {
        "immagine": "IR_0001.jpg",
        "cartella": "IR_0001",
        "data_ora": "2026-06-30 14:23:11",
        "direzione_deg": 210
      }
    }
  ]
}
```

---

## `originali/` — kit di riapertura

`<base>.jpg` (originale FLIR invariato) + `<base>.json` (sessione). È l'unico modo
di riaprire il lavoro: si apre l'originale in Warmish e si carica il `.json`.

Non c'è export della matrice di temperatura per-pixel. Il caso "dati fuori da
Warmish" è coperto da `aree.csv` per le statistiche; per la griglia completa si
riapre l'originale in Warmish (che ora è un URL, senza installazione). Un
`temperatura.tif` 16-bit si aggiunge solo se emerge una richiesta reale.

Checkbox **"Includi originali"**, default **ON** (sia export singolo sia batch da
cartella), disattivabile. Con originali OFF, `originali/` contiene solo i `.json` e
una nota che servono anche le immagini di partenza.

---

## `errori.txt`

Solo se qualche file fallisce. Una riga per file: `<nome>: <messaggio>`.

---

## Interattivo vs batch

- **"Esporta (.zip)"** — un solo bottone. Immagine singola → zip con una sola
  cartella-immagine + `originali/` + `aree.csv` (0 o più righe) + `manifest.json`
  + `punti_scatto.geojson` se c'è GPS.
- **"Salva sessione (.json)"** — resta come bottone leggero separato: checkpoint
  durante il lavoro senza generare i raster.
- **"Salva sessione cartella (.json)"** — reintrodotto (sezione "Cartella
  aperta"). Un solo file `warmish_folder_session` con lo stato di edit di ogni
  immagine (chiave = path relativo, come il desktop) più un blocco `workspace`
  (immagine attiva, selezione filmstrip, "includi originali", modalità aree —
  estensione web, il desktop ignora la chiave). È il checkpoint della cartella:
  nessun raster, si riapre ri-selezionando la cartella e trascinando il `.json`.
  Il kit `originali/` nello ZIP resta il pacchetto di consegna completo; questo è
  l'equivalente leggero per il lavoro in corso.
- Spariscono: "Esporta PNG", "Esporta visibile", "Esporta CSV aree".

---

## File toccati (fatto)

- `src/core/pipeline.ts` — riscrittura del set di output, `DECORATED_LONG_EDGE`
  (2560, max 4×), render deterministico, `ImageResult` con righe/manifest/geo
- `src/lib/batch.worker.ts` — struttura zip a cartelle sotto
  `warmish_export_<data>/`, aggregati, `originali/`, `includeOriginals`
- `src/core/render.ts` — `drawLegendH` (barra orizzontale in basso); la barra
  del viewer live resta verticale a destra
- `src/core/report.ts` (nuovo) — `buildAreeCsv` (`;`, `,`, BOM, CRLF,
  `geometria` piatta), `buildManifest`, `buildGeojson`
- `src/core/roi.ts` — `RoiStats` porta anche `minX/minY/maxX/maxY`
- `src/core/exif.ts` — `extractExifApp1` / `injectExifApp1` (sostituzione),
  `parseCapture` (camera + data_ora)
- `src/App.svelte` — `currentFile`, `dispatchExport`, bottone "Esporta (.zip)",
  checkbox "Includi originali", rimossi i 4 bottoni vecchi e "sessione cartella"
- `tests/phase3.ts` (CSV) e `tests/ui-smoke.ts` (struttura zip, GPS nel visibile)

`npm test` e `npm run test:ui` verdi.
