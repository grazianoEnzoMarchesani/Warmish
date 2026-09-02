/**
 * Bends the guided-tour trail around building footprints so it doesn't cut
 * straight across roofs.
 *
 * The footprints come from the very same OpenFreeMap vector tiles the "Minimal"
 * basemap already draws: protomaps-leaflet decodes the MVT for us, so this adds
 * no dependency and no new network origin. It only runs while a "Minimal"
 * basemap is active — that's the one case where those tiles are already in play.
 *
 * Method: a visibility graph. For each pair of consecutive shots we first check
 * whether the straight line clears every building; if it does we keep it. If it
 * doesn't, we build a graph from the building corners (each nudged a couple of
 * metres outward) plus the two endpoints, join every pair that can see each
 * other, and run A* for the shortest bent path.
 *
 * The vector footprints are generalised and some buildings are missing, so the
 * result dodges *most* buildings, not all — which is fine for a fly-through. On
 * anything unexpected (network error, an oversized area, a segment that would
 * need a wildly long detour) it silently falls back to the straight line.
 */
import type * as PM from 'protomaps-leaflet';

/** `[lat, lon]` — matches Leaflet's `LatLngTuple`, so a caller can hand the
 *  result straight to a polyline. */
export type LatLon = [number, number];

export interface RouteSegment {
  /** Polyline from one shot to the next: `[from, ...detour, to]` when it had to
   *  bend, just `[from, to]` otherwise. Always starts/ends on the exact stops. */
  path: LatLon[];
  /** `true` when the polyline reaches the next shot without touching a building
   *  (straight-and-clear, or successfully routed around). `false` when the line
   *  is forced to cross one — draw it dashed to show the gap couldn't be closed. */
  clear: boolean;
}

interface Vec {
  x: number;
  y: number;
}
type Bbox = [number, number, number, number]; // minX, minY, maxX, maxY

interface Obstacle {
  /** Exterior ring, local metres, open (no repeated closing vertex). */
  ring: Vec[];
  bbox: Bbox;
}

const CLEARANCE = 3.5; // metres to keep off the walls
const RING_TOLERANCE = 0.3; // metres — drop sub-this footprint wiggle on load
const MAX_TILES = 16; // bail past this — the shots are too far apart to matter
const MAX_CANDIDATES = 40; // obstacles fed to one segment's visibility graph
const MAX_NODES = 420; // graph nodes per blocked segment
const TIME_BUDGET_MS = 4000; // total; leftover segments stay straight

// --- slippy-tile maths ------------------------------------------------------

const lon2tileX = (lon: number, z: number) => ((lon + 180) / 360) * 2 ** z;
const lat2tileY = (lat: number, z: number) => {
  const s = Math.sin((lat * Math.PI) / 180);
  return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * 2 ** z;
};
const tileX2lon = (x: number, z: number) => (x / 2 ** z) * 360 - 180;
const tileY2lat = (y: number, z: number) =>
  (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z))) * 180) / Math.PI;

/** Local equirectangular projection around an origin — good enough over the few
 *  hundred metres between two consecutive shots. */
function projector(lat0: number, lon0: number) {
  const mPerLat = 111132;
  const mPerLon = 111320 * Math.cos((lat0 * Math.PI) / 180) || 1;
  return {
    fwd: (lat: number, lon: number): Vec => ({
      x: (lon - lon0) * mPerLon,
      y: (lat - lat0) * mPerLat,
    }),
    inv: (v: Vec): LatLon => [lat0 + v.y / mPerLat, lon0 + v.x / mPerLon],
  };
}

// --- small vector helpers --------------------------------------------------

const sub = (a: Vec, b: Vec): Vec => ({ x: a.x - b.x, y: a.y - b.y });
const dist = (a: Vec, b: Vec) => Math.hypot(a.x - b.x, a.y - b.y);
const cross = (a: Vec, b: Vec) => a.x * b.y - a.y * b.x;
function unit(v: Vec): Vec {
  const l = Math.hypot(v.x, v.y) || 1;
  return { x: v.x / l, y: v.y / l };
}

function ringBbox(ring: Vec[]): Bbox {
  let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
  for (const p of ring) {
    if (p.x < a) a = p.x;
    if (p.y < b) b = p.y;
    if (p.x > c) c = p.x;
    if (p.y > d) d = p.y;
  }
  return [a, b, c, d];
}
const bboxOverlap = (p: Bbox, q: Bbox) =>
  p[0] <= q[2] && q[0] <= p[2] && p[1] <= q[3] && q[1] <= p[3];

/** Even-odd ray cast. Points exactly on the boundary may go either way — that's
 *  acceptable here (the path is allowed to graze a wall). */
function pointInRing(p: Vec, ring: Vec[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if (a.y > p.y !== b.y > p.y) {
      const t = (p.y - a.y) / (b.y - a.y);
      if (p.x < a.x + t * (b.x - a.x)) inside = !inside;
    }
  }
  return inside;
}

/** True only when the open segments properly cross — a shared endpoint or a
 *  T-touch counts as clear, so the path can hug a corner. */
function properCross(a: Vec, b: Vec, c: Vec, d: Vec): boolean {
  const ab = sub(b, a), cd = sub(d, c);
  const d1 = cross(ab, sub(c, a));
  const d2 = cross(ab, sub(d, a));
  const d3 = cross(cd, sub(a, c));
  const d4 = cross(cd, sub(b, c));
  const E = 1e-6;
  return (
    ((d1 > E && d2 < -E) || (d1 < -E && d2 > E)) &&
    ((d3 > E && d4 < -E) || (d3 < -E && d4 > E))
  );
}

function closestOnSeg(p: Vec, a: Vec, b: Vec): Vec {
  const ab = sub(b, a);
  const len2 = ab.x * ab.x + ab.y * ab.y || 1e-9;
  let t = ((p.x - a.x) * ab.x + (p.y - a.y) * ab.y) / len2;
  t = Math.max(0, Math.min(1, t));
  return { x: a.x + ab.x * t, y: a.y + ab.y * t };
}

function polylineLength(pts: Vec[]): number {
  let s = 0;
  for (let i = 1; i < pts.length; i++) s += dist(pts[i - 1], pts[i]);
  return s;
}

/** Perpendicular distance from point `p` to segment `ab`. */
function pointSegDist(p: Vec, a: Vec, b: Vec): number {
  return dist(p, closestOnSeg(p, a, b));
}

/** Closest approach between two segments (0 when they cross). */
function segSegDist(a: Vec, b: Vec, c: Vec, d: Vec): number {
  if (properCross(a, b, c, d)) return 0;
  return Math.min(
    pointSegDist(a, c, d), pointSegDist(b, c, d),
    pointSegDist(c, a, b), pointSegDist(d, a, b),
  );
}

/** Distance from segment `ab` to a footprint (0 if it enters). */
function segRingDist(a: Vec, b: Vec, ring: Vec[]): number {
  if (pointInRing(a, ring) || pointInRing(b, ring)) return 0;
  let m = Infinity;
  for (let k = 0; k < ring.length; k++) {
    m = Math.min(m, segSegDist(a, b, ring[k], ring[(k + 1) % ring.length]));
    if (m === 0) return 0;
  }
  return m;
}

/** Radial Douglas–Peucker — enough to shed the vertex noise in dense
 *  footprints without moving a wall more than `tol` metres. */
function simplifyRing(ring: Vec[], tol: number): Vec[] {
  if (ring.length <= 4) return ring;
  const keep = new Uint8Array(ring.length);
  keep[0] = 1;
  const stack: [number, number][] = [[0, ring.length - 1]];
  while (stack.length) {
    const [lo, hi] = stack.pop()!;
    let far = -1, fd = tol;
    for (let i = lo + 1; i < hi; i++) {
      const d = pointSegDist(ring[i], ring[lo], ring[hi]);
      if (d > fd) {
        fd = d;
        far = i;
      }
    }
    if (far !== -1) {
      keep[far] = 1;
      stack.push([lo, far], [far, hi]);
    }
  }
  const out: Vec[] = [];
  for (let i = 0; i < ring.length; i++) if (keep[i]) out.push(ring[i]);
  return out.length >= 3 ? out : ring;
}

const unionBbox = (p: Bbox, q: Bbox): Bbox => [
  Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[2], q[2]), Math.max(p[3], q[3]),
];
const inflateBbox = (b: Bbox, m: number): Bbox => [b[0] - m, b[1] - m, b[2] + m, b[3] + m];

// --- outward offsets -------------------------------------------------------

/** A building corner nudged out along the edge bisector. `null` if there's no
 *  room to place it outside the footprint (a deep reflex notch). */
function outwardVertex(ring: Vec[], k: number, clear: number): Vec | null {
  const n = ring.length;
  const prev = ring[(k - 1 + n) % n], cur = ring[k], next = ring[(k + 1) % n];
  const e1 = unit(sub(cur, prev)), e2 = unit(sub(next, cur));
  let nx = -(e1.y + e2.y), ny = e1.x + e2.x;
  if (Math.hypot(nx, ny) < 1e-9) {
    nx = -e2.y;
    ny = e2.x;
  }
  const l = Math.hypot(nx, ny) || 1;
  nx /= l;
  ny /= l;
  let cand: Vec = { x: cur.x + nx * clear, y: cur.y + ny * clear };
  if (pointInRing(cand, ring)) {
    cand = { x: cur.x - nx * clear, y: cur.y - ny * clear };
    if (pointInRing(cand, ring)) return null;
  }
  return cand;
}

/** Nearest point on a footprint's boundary, pushed `clear` metres outward —
 *  used when a shot's own coordinate falls inside a building. */
function outwardPoint(p: Vec, ring: Vec[], clear: number): Vec {
  let best = ring[0], bd = Infinity, nrm: Vec = { x: 1, y: 0 };
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    const q = closestOnSeg(p, a, b);
    const d = dist(p, q);
    if (d < bd) {
      bd = d;
      best = q;
      const e = unit(sub(b, a));
      nrm = { x: -e.y, y: e.x };
    }
  }
  let cand: Vec = { x: best.x + nrm.x * clear, y: best.y + nrm.y * clear };
  if (pointInRing(cand, ring)) cand = { x: best.x - nrm.x * clear, y: best.y - nrm.y * clear };
  return cand;
}

// --- visibility graph + A* -----------------------------------------------

function blocked(p: Vec, q: Vec, obs: Obstacle[]): boolean {
  const segBox: Bbox = [
    Math.min(p.x, q.x), Math.min(p.y, q.y), Math.max(p.x, q.x), Math.max(p.y, q.y),
  ];
  const mid = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
  for (const o of obs) {
    if (!bboxOverlap(o.bbox, segBox)) continue;
    const r = o.ring;
    for (let k = 0; k < r.length; k++) {
      if (properCross(p, q, r[k], r[(k + 1) % r.length])) return true;
    }
    if (pointInRing(mid, r)) return true;
  }
  return false;
}

/** Shortest node path from index 0 to index 1, or `null`. */
function aStar(nodes: Vec[], obs: Obstacle[]): Vec[] | null {
  const N = nodes.length;
  const GOAL = 1;
  const g = new Float64Array(N).fill(Infinity);
  const came = new Int32Array(N).fill(-1);
  const closed = new Uint8Array(N);
  const vis = new Map<number, boolean>();
  const visible = (i: number, j: number) => {
    const key = i < j ? i * N + j : j * N + i;
    let v = vis.get(key);
    if (v === undefined) {
      v = !blocked(nodes[i], nodes[j], obs);
      vis.set(key, v);
    }
    return v;
  };

  g[0] = 0;
  const open = new Set<number>([0]);
  while (open.size) {
    let cur = -1, bestF = Infinity;
    for (const i of open) {
      const f = g[i] + dist(nodes[i], nodes[GOAL]);
      if (f < bestF) {
        bestF = f;
        cur = i;
      }
    }
    if (cur === GOAL) break;
    open.delete(cur);
    closed[cur] = 1;
    for (let j = 0; j < N; j++) {
      if (j === cur || closed[j]) continue;
      const tentative = g[cur] + dist(nodes[cur], nodes[j]);
      if (tentative >= g[j]) continue;
      if (!visible(cur, j)) continue;
      g[j] = tentative;
      came[j] = cur;
      open.add(j);
    }
  }
  if (came[GOAL] === -1) return null;

  const path: Vec[] = [];
  for (let i = GOAL; i !== -1; i = came[i]) path.push(nodes[i]);
  return path.reverse();
}

/** Drop near-duplicate vertices only. (Collinear-merging is left out on
 *  purpose: it can straighten a leg back across the corner it was routed to
 *  avoid, and the graph path is already minimal.) */
function simplify(pts: Vec[]): Vec[] {
  const out: Vec[] = [];
  for (const p of pts) {
    if (out.length && dist(out[out.length - 1], p) < 0.5) continue;
    out.push(p);
  }
  return out;
}

/** Last-resort detour: skirt the combined bounding box of the buildings that
 *  actually block the line, whichever way round is shorter. */
function bboxDetour(a: Vec, b: Vec, blockers: Obstacle[]): Vec[] | null {
  let box = blockers[0].bbox;
  for (const o of blockers) box = unionBbox(box, o.bbox);
  const [x0, y0, x1, y1] = inflateBbox(box, CLEARANCE);
  const tl = { x: x0, y: y1 }, tr = { x: x1, y: y1 };
  const bl = { x: x0, y: y0 }, br = { x: x1, y: y0 };
  const routes = [
    [tl, tr], [tr, tl], [bl, br], [br, bl],
    [tl, bl], [bl, tl], [tr, br], [br, tr],
  ];
  let best: Vec[] | null = null, bestLen = Infinity;
  for (const r of routes) {
    const pts = [a, ...r, b];
    let ok = true;
    for (let i = 1; i < pts.length && ok; i++) ok = !blocked(pts[i - 1], pts[i], blockers);
    if (!ok) continue;
    const len = polylineLength(pts);
    if (len < bestLen) {
      bestLen = len;
      best = r;
    }
  }
  return best;
}

/** Cheap fallback: one bend point, pushed off the straight line perpendicular
 *  by a growing amount until both halves clear every obstacle. */
function perpDetour(a: Vec, b: Vec, obs: Obstacle[]): Vec[] | null {
  const dir = unit(sub(b, a));
  const perp = { x: -dir.y, y: dir.x };
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const reach = Math.min(90, dist(a, b) * 1.2 + 10);
  for (let d = 6; d <= reach; d += 6) {
    for (const side of [1, -1]) {
      const w = { x: mid.x + perp.x * side * d, y: mid.y + perp.y * side * d };
      if (!blocked(a, w, obs) && !blocked(w, b, obs)) return [w];
    }
  }
  return null;
}

/**
 * `clear`   — the straight line already misses every building.
 * `bent`    — `via` are interior waypoints that steer around them.
 * `blocked` — the line crosses buildings and no way round was found; the caller
 *             should keep the straight line but mark it (dashed) as unavoidable.
 */
type Bend = { kind: 'clear' } | { kind: 'bent'; via: Vec[] } | { kind: 'blocked' };

function bendSegment(a: Vec, b: Vec, all: Obstacle[]): Bend {
  const span = dist(a, b);

  // Buildings the straight line actually hits — the ones we have to get around.
  const aInside = all.find((o) => bboxOverlap(o.bbox, [a.x, a.y, a.x, a.y]) && pointInRing(a, o.ring)) ?? null;
  const bInside = all.find((o) => bboxOverlap(o.bbox, [b.x, b.y, b.x, b.y]) && pointInRing(b, o.ring)) ?? null;
  const segBox: Bbox = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)];
  const blockers = all.filter(
    (o) => o === aInside || o === bInside ||
      (bboxOverlap(o.bbox, segBox) && segRingDist(a, b, o.ring) === 0),
  );
  if (!blockers.length) return { kind: 'clear' };

  // A wider set for detour room / to not clip a neighbour, kept small.
  const reach = Math.min(120, Math.max(25, span * 0.35));
  const grown = inflateBbox(segBox, reach);
  let candidates = all.filter((o) => bboxOverlap(o.bbox, grown) && segRingDist(a, b, o.ring) <= reach);
  if (candidates.length > MAX_CANDIDATES) {
    candidates = candidates
      .map((o) => ({ o, d: blockers.includes(o) ? -1 : segRingDist(a, b, o.ring) }))
      .sort((p, q) => p.d - q.d)
      .slice(0, MAX_CANDIDATES)
      .map((p) => p.o);
  }

  const start = aInside ? outwardPoint(a, aInside.ring, CLEARANCE) : a;
  const goal = bInside ? outwardPoint(b, bInside.ring, CLEARANCE) : b;

  let nodePath: Vec[] | null = null;
  const nodes: Vec[] = [start, goal];
  for (const o of candidates) {
    for (let k = 0; k < o.ring.length; k++) {
      const v = outwardVertex(o.ring, k, CLEARANCE);
      if (v) nodes.push(v);
    }
  }
  if (nodes.length <= MAX_NODES) nodePath = aStar(nodes, candidates);

  const detour = nodePath
    ? nodePath.slice(1, -1)
    : perpDetour(start, goal, candidates) ?? bboxDetour(a, b, blockers);
  if (!detour) return { kind: 'blocked' };

  const full = simplify([...(aInside ? [a] : []), start, ...detour, goal, ...(bInside ? [b] : [])]);
  const interior = full.slice(1, -1);
  if (!interior.length) return { kind: 'blocked' };

  const line = [a, ...interior, b];
  if (polylineLength(line) > span * 2.2 + 60) return { kind: 'blocked' }; // implausibly long detour

  // Re-check the finished line against *every* nearby footprint (A* only ever
  // saw the candidate subset, and simplify() may have straightened a leg across
  // a corner). If it still clips a building — indoor hops from a snapped
  // endpoint aside — keep the straight line instead.
  const lineBox = inflateBbox(line.reduce<Bbox>(
    (bx, p) => unionBbox(bx, [p.x, p.y, p.x, p.y]),
    [Infinity, Infinity, -Infinity, -Infinity],
  ), 5);
  const near = all.filter((o) => bboxOverlap(o.bbox, lineBox));
  const from = aInside ? 1 : 0;
  const to = line.length - (bInside ? 2 : 1);
  for (let i = from; i < to; i++) {
    if (legHitsBuilding(line[i], line[i + 1], near)) return { kind: 'blocked' };
  }
  return { kind: 'bent', via: interior };
}

/** Thorough (not fast) leg test for the final validation: edge crossings plus
 *  a fistful of interior samples, so a leg that clips a corner between two
 *  near-vertex crossings — which `blocked()` waves through — is still caught. */
function legHitsBuilding(p: Vec, q: Vec, obs: Obstacle[]): boolean {
  const segBox: Bbox = [
    Math.min(p.x, q.x), Math.min(p.y, q.y), Math.max(p.x, q.x), Math.max(p.y, q.y),
  ];
  for (const o of obs) {
    if (!bboxOverlap(o.bbox, segBox)) continue;
    const r = o.ring;
    for (let k = 0; k < r.length; k++) {
      if (properCross(p, q, r[k], r[(k + 1) % r.length])) return true;
    }
    for (let s = 1; s <= 11; s++) {
      const t = s / 12;
      if (pointInRing({ x: p.x + (q.x - p.x) * t, y: p.y + (q.y - p.y) * t }, r)) return true;
    }
  }
  return false;
}

// --- entry point ---------------------------------------------------------

/**
 * @param stops   located shots in tour order, `[lat, lon]`
 * @param tilejsonUrl  the OpenFreeMap TileJSON the basemap uses
 * @returns one {@link RouteSegment} per consecutive pair (`stops.length - 1` of
 *          them). If the footprints can't be loaded at all every segment comes
 *          back straight and `clear` (the caller then behaves as before).
 */
export async function routeAroundBuildings(
  stops: LatLon[],
  tilejsonUrl: string,
): Promise<RouteSegment[]> {
  const segments: RouteSegment[] = [];
  for (let i = 0; i < stops.length - 1; i++) {
    segments.push({ path: [stops[i], stops[i + 1]], clear: true });
  }
  if (stops.length < 2) return segments;

  let minLat = 90, minLon = 180, maxLat = -90, maxLon = -180;
  for (const [la, lo] of stops) {
    minLat = Math.min(minLat, la);
    maxLat = Math.max(maxLat, la);
    minLon = Math.min(minLon, lo);
    maxLon = Math.max(maxLon, lo);
  }
  const midLat = (minLat + maxLat) / 2;
  const padLat = 120 / 111132;
  const padLon = 120 / (111320 * Math.cos((midLat * Math.PI) / 180) || 1);
  minLat -= padLat;
  maxLat += padLat;
  minLon -= padLon;
  maxLon += padLon;

  const pm = await import('protomaps-leaflet');
  const tj = await fetch(tilejsonUrl, { cache: 'force-cache' }).then((r) => {
    if (!r.ok) throw new Error(`TileJSON ${r.status}`);
    return r.json();
  });
  const url: string = tj.tiles[0];
  const z: number = Math.min(14, tj.maxzoom ?? 14);

  const x0 = Math.floor(lon2tileX(minLon, z)), x1 = Math.floor(lon2tileX(maxLon, z));
  const y0 = Math.floor(lat2tileY(maxLat, z)), y1 = Math.floor(lat2tileY(minLat, z));
  const tileCount = (x1 - x0 + 1) * (y1 - y0 + 1);
  if (tileCount < 1 || tileCount > MAX_TILES) return segments;

  const lat0 = midLat, lon0 = (minLon + maxLon) / 2;
  const { fwd, inv } = projector(lat0, lon0);

  const cache = new pm.TileCache(new pm.ZxySource(url, false), 4096);
  const tiles: PM.Zxy[] = [];
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) tiles.push({ z, x, y });

  const obstacles: Obstacle[] = [];
  await Promise.all(
    tiles.map(async (t) => {
      let layers: Map<string, PM.Feature[]>;
      try {
        layers = await cache.get(t);
      } catch {
        return;
      }
      const feats = layers.get('building');
      if (!feats) return;
      for (const f of feats) {
        if (f.geomType !== pm.GeomType.Polygon) continue;
        for (const r of f.geom) {
          if (r.length < 4) continue;
          if (pm.isCcw(r)) continue; // interior ring (courtyard) — keep the block solid
          const ring: Vec[] = [];
          for (const p of r) {
            const lon = tileX2lon(t.x + p.x / 4096, z);
            const lat = tileY2lat(t.y + p.y / 4096, z);
            ring.push(fwd(lat, lon));
          }
          const first = ring[0], last = ring[ring.length - 1];
          if (Math.abs(first.x - last.x) < 1e-6 && Math.abs(first.y - last.y) < 1e-6) ring.pop();
          if (ring.length < 3) continue;
          const simple = simplifyRing(ring, RING_TOLERANCE);
          obstacles.push({ ring: simple, bbox: ringBbox(simple) });
        }
      }
    }),
  );
  if (!obstacles.length) return segments;

  const deadline = performance.now() + TIME_BUDGET_MS;
  for (let i = 0; i < stops.length - 1; i++) {
    if (performance.now() > deadline) break;
    const a = fwd(stops[i][0], stops[i][1]);
    const b = fwd(stops[i + 1][0], stops[i + 1][1]);
    if (dist(a, b) < 1) continue;
    try {
      const bent = bendSegment(a, b, obstacles);
      if (bent.kind === 'bent') {
        segments[i] = { path: [stops[i], ...bent.via.map(inv), stops[i + 1]], clear: true };
      } else if (bent.kind === 'blocked') {
        segments[i] = { path: [stops[i], stops[i + 1]], clear: false };
      }
    } catch {
      /* keep the straight segment */
    }
    await Promise.resolve(); // yield between segments
  }
  return segments;
}
