# Warmish Geotag

Pagina statica autonoma in `warmish-web/public/geotag/`, quindi servita da Warmish
Web all'URL **`geotag/index.html`** (dev: `http://localhost:5173/geotag/index.html`;
produzione: `<sito>/geotag/`). Nell'app la si apre dal link **"Geotag → posiziona
le foto sulla mappa e correggi il GPS"** nella barra laterale, e dai suggerimenti
nella vista Mappa quando le foto non hanno GPS o hanno tutte la stessa coordinata.

Il link punta a `geotag/index.html` e non a `geotag/` perché il dev server di Vite
fa da fallback all'`index.html` dell'app per gli URL "cartella".

Serve a posizionare a mano su una mappa le foto FLIR/JPEG con GPS mancante o
sbagliato (tipico dei telefoni che scrivono una sola posizione in cache per
l'intera sessione) e a riscrivere le coordinate negli EXIF.

Non condivide codice con l'app: è HTML/CSS/JS in un unico file più `lib/`. Non
modifica gli originali — l'output è uno ZIP.

## Uso

Layout a tre colonne: a **sinistra** l'elenco delle foto e i comandi di
caricamento/esportazione, al **centro** la mappa, a **destra** il pannello
**Anteprima e coordinate** della foto selezionata. Ogni sidebar si comprime con
il pulsante « / » nella sua intestazione e si riapre dalla linguetta sul bordo
della mappa; lo stato è ricordato nel browser.

1. **Scegli foto…** o **Scegli cartella…** (solo JPEG).
2. Seleziona una foto nella striscia a sinistra. Il pannello a destra mostra
   la **foto visibile incorporata** nel file FLIR (non la resa termica, spesso
   illeggibile); clic sull'anteprima per ingrandirla a schermo intero (Esc per
   chiudere). Se il file non ha una foto visibile si vede l'anteprima termica.
3. **Clic sulla mappa** = posiziona quella foto. Trascina il pallino per spostarlo.
   **Shift+clic** (o **clic destro**) su un punto = orienta la foto verso quel
   punto. La direzione si può anche digitare nel campo apposito.
4. Il cerchietto tratteggiato è la posizione originale della fotocamera.
   **Usa posizione originale** la riprende; **Copia posizione → tutte / → foto non
   posizionate** replica la posizione corrente sulle altre (utile quando gli
   scatti sono dallo stesso punto).
5. **Scarica ZIP geotaggato** — ogni foto posizionata esce con il GPS riscritto
   negli EXIF; le foto non posizionate restano identiche. Nello ZIP c'è anche
   `geotag.csv` con l'elenco delle coordinate.

Il lavoro viene salvato nel browser (localStorage) e si può esportare/importare
come `.json` con **Esporta lavoro / Importa lavoro**.

## Cosa viene scritto

Nel blocco EXIF-GPS standard (l'IFD puntato dal tag `GPSInfo`):

- `GPSLatitude` / `GPSLatitudeRef`, `GPSLongitude` / `GPSLongitudeRef`, `GPSMapDatum` = WGS84
- `GPSImgDirection` / `GPSImgDirectionRef` = `T` (nord vero) — solo se imposti una direzione
- `GPSAltitude` / `GPSAltitudeRef` — solo se imposti un'altitudine

**I dati radiometrici FLIR non vengono toccati.** Verificato in
`tests/geotag-ui.ts`: dopo la riscrittura, dimensioni sensore, costanti di Planck,
immagine visibile incorporata e range di temperatura restano identici, e Warmish
legge le nuove coordinate.

Il GPS che alcune fotocamere FLIR duplicano *dentro* il blocco APP1 FLIR **non**
viene aggiornato (è molto più difficile e Warmish non lo legge): resta il valore
originale. Chi legge quel blocco (es. FLIR Tools) vedrà ancora la vecchia
posizione; tutto il resto — Warmish, ExifTool `Composite:GPSPosition`, i visori
foto, le mappe — usa il blocco EXIF standard che questo strumento riscrive.

## Librerie

In `lib/` (nessuna CDN): [Leaflet](https://leafletjs.com) 1.9.4,
[piexifjs](https://github.com/hMatoba/piexifjs) 1.0.6,
[fflate](https://github.com/101arrowz/fflate) 0.8.2. I tasselli della mappa
(Esri / OpenStreetMap) sono l'unica cosa che richiede rete — come la vista Mappa
dell'app.
