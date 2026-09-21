import type { GraphData, GraphEdge } from "../types/graph";

interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  group: string;
  degree: number;
}

const NODE_RADIUS = 14;
const MIN_GAP = NODE_RADIUS * 2 + 6;

function buildAdjacency(edges: GraphEdge[]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  const touch = (a: string, b: string) => {
    if (!adj.has(a)) adj.set(a, new Set());
    adj.get(a)!.add(b);
  };
  for (const e of edges) {
    touch(e.from, e.to);
    touch(e.to, e.from);
  }
  return adj;
}

/** Pull isolated nodes toward the main mass with soft anchor links. */
function anchorIsolated(
  nodes: SimNode[],
): { source: SimNode; target: SimNode; strength: number; distance: number }[] {
  const connected = nodes.filter((n) => n.degree > 0);
  const isolated = nodes.filter((n) => n.degree === 0);
  if (!connected.length || !isolated.length) return [];

  const anchors: { source: SimNode; target: SimNode; strength: number; distance: number }[] = [];

  for (const iso of isolated) {
    let best: SimNode | null = null;
    let bestScore = Infinity;

    for (const c of connected) {
      const sameGroup = c.group === iso.group ? 0 : 80;
      const dx = c.x - iso.x;
      const dy = c.y - iso.y;
      const dist = Math.hypot(dx, dy);
      const score = dist + sameGroup;
      if (score < bestScore) {
        bestScore = score;
        best = c;
      }
    }

    if (best) {
      anchors.push({ source: iso, target: best, strength: 0.08, distance: MIN_GAP * 2.5 });
    }
  }

  return anchors;
}

function runSimulation(
  nodes: SimNode[],
  links: { source: SimNode; target: SimNode; strength: number; distance: number }[],
  cx: number,
  cy: number,
  ticks: number,
): void {
  for (let tick = 0; tick < ticks; tick++) {
    const alpha = Math.pow(1 - tick / ticks, 1.1);

    for (const link of links) {
      const dx = link.target.x - link.source.x;
      const dy = link.target.y - link.source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const force = ((dist - link.distance) / dist) * link.strength * alpha;
      link.source.vx += dx * force;
      link.source.vy += dy * force;
      link.target.vx -= dx * force;
      link.target.vy -= dy * force;
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.hypot(dx, dy) || 0.01;

        const repulse = (6500 / (dist * dist)) * alpha;
        const rx = (dx / dist) * repulse;
        const ry = (dy / dist) * repulse;
        a.vx -= rx;
        a.vy -= ry;
        b.vx += rx;
        b.vy += ry;

        if (dist < MIN_GAP) {
          const push = ((MIN_GAP - dist) / dist) * 0.7;
          a.x -= dx * push;
          a.y -= dy * push;
          b.x += dx * push;
          b.y += dy * push;
        }
      }
    }

    for (const node of nodes) {
      const pull = node.degree === 0 ? 0.006 : 0.003;
      node.vx += (cx - node.x) * pull * alpha;
      node.vy += (cy - node.y) * pull * alpha;
      node.vx *= 0.52;
      node.vy *= 0.52;
      node.x += node.vx;
      node.y += node.vy;
    }
  }
}

/** Force-directed layout — one cohesive cluster, outliers capped for fit. */
export function computeForceLayout(
  data: GraphData,
): Map<string, { x: number; y: number }> {
  return computeForceLayoutWithMeta(data).positions;
}

export interface LayoutResult {
  positions: Map<string, { x: number; y: number }>;
  coreIds: Set<string>;
}

export function computeForceLayoutWithMeta(data: GraphData): LayoutResult {
  const raw = runForceSimulation(data);
  const entries = [...raw.entries()].map(([id, p]) => ({ id, ...p }));
  const { core } = splitCoreOutliers(entries);
  const coreIds = new Set(core.map((e) => e.id));
  return { positions: normalizePositions(raw), coreIds };
}

function runForceSimulation(
  data: GraphData,
): Map<string, { x: number; y: number }> {
  const n = data.nodes.length;
  const adj = buildAdjacency(data.edges);

  const spread = Math.max(400, Math.sqrt(n) * 55);
  const cx = spread;
  const cy = spread;

  const simNodes = new Map<string, SimNode>();

  for (const node of data.nodes) {
    const degree = adj.get(node.id)?.size ?? 0;
    simNodes.set(node.id, {
      id: node.id,
      x: cx + (Math.random() - 0.5) * spread * 0.35,
      y: cy + (Math.random() - 0.5) * spread * 0.35,
      vx: 0,
      vy: 0,
      group: node.group,
      degree,
    });
  }

  const edgeLinks = data.edges
    .filter((e) => simNodes.has(e.from) && simNodes.has(e.to))
    .map((e) => ({
      source: simNodes.get(e.from)!,
      target: simNodes.get(e.to)!,
      strength: 0.14,
      distance: Math.max(55, Math.min(95, 40 + n * 0.25)),
    }));

  const nodes = [...simNodes.values()];
  const ticks = Math.min(700, 280 + n * 2);

  runSimulation(nodes, edgeLinks, cx, cy, ticks);

  const anchorLinks = anchorIsolated(nodes);
  runSimulation(nodes, [...edgeLinks, ...anchorLinks], cx, cy, Math.floor(ticks * 0.45));

  const positions = new Map<string, { x: number; y: number }>();
  for (const node of nodes) {
    positions.set(node.id, { x: node.x, y: node.y });
  }

  return positions;
}

/** Scale using core nodes only — outliers are clamped near the cluster edge. */
function normalizePositions(
  positions: Map<string, { x: number; y: number }>,
): Map<string, { x: number; y: number }> {
  const entries = [...positions.entries()].map(([id, p]) => ({ id, ...p }));
  if (!entries.length) return positions;

  const { core, outliers, cx, cy, maxCoreDist } = splitCoreOutliers(entries);

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const p of core) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  }

  const w = maxX - minX || 1;
  const h = maxY - minY || 1;
  const target = 900;
  const scale = target / Math.max(w, h);
  const pad = 80;

  const out = new Map<string, { x: number; y: number }>();
  const coreCenter = {
    x: ((minX + maxX) / 2 - minX) * scale + pad,
    y: ((minY + maxY) / 2 - minY) * scale + pad,
  };
  const maxRadius = Math.max(w, h) * scale * 0.55;

  for (const p of core) {
    out.set(p.id, {
      x: (p.x - minX) * scale + pad,
      y: (p.y - minY) * scale + pad,
    });
  }

  for (const p of outliers) {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const dist = Math.hypot(dx, dy) || 1;
    const clampDist = Math.min(dist, maxCoreDist * 1.08);
    const nx = cx + (dx / dist) * clampDist;
    const ny = cy + (dy / dist) * clampDist;
    let sx = (nx - minX) * scale + pad;
    let sy = (ny - minY) * scale + pad;

    const odx = sx - coreCenter.x;
    const ody = sy - coreCenter.y;
    const od = Math.hypot(odx, ody);
    if (od > maxRadius) {
      sx = coreCenter.x + (odx / od) * maxRadius;
      sy = coreCenter.y + (ody / od) * maxRadius;
    }

    out.set(p.id, { x: sx, y: sy });
  }

  return out;
}

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  return percentile(s, 0.5);
}

/** IQR-based outlier split — used for normalize + fitView. */
function splitCoreOutliers(
  entries: { id: string; x: number; y: number }[],
): {
  core: { id: string; x: number; y: number; d: number }[];
  outliers: { id: string; x: number; y: number; d: number }[];
  cx: number;
  cy: number;
  maxCoreDist: number;
} {
  const cx = median(entries.map((e) => e.x));
  const cy = median(entries.map((e) => e.y));

  const ranked = entries
    .map((e) => ({ ...e, d: Math.hypot(e.x - cx, e.y - cy) }))
    .sort((a, b) => a.d - b.d);

  const distances = ranked.map((e) => e.d);
  const q1 = percentile(distances, 0.25);
  const q3 = percentile(distances, 0.75);
  const iqr = q3 - q1;
  const p90 = percentile(distances, 0.9);
  const threshold = Math.min(q3 + 1.2 * iqr, p90 * 1.05);

  const core = ranked.filter((e) => e.d <= threshold);
  const outliers = ranked.filter((e) => e.d > threshold);
  const maxCoreDist = core.length ? core[core.length - 1].d : threshold;

  return { core, outliers, cx, cy, maxCoreDist };
}

export function getCoreNodeIds(
  positions: Map<string, { x: number; y: number }>,
): Set<string> {
  const entries = [...positions.entries()].map(([id, p]) => ({ id, ...p }));
  const { core } = splitCoreOutliers(entries);
  return new Set(core.map((e) => e.id));
}

export { buildAdjacency };

export function expandNeighborhood(
  edges: GraphEdge[],
  seedIds: Set<string>,
  hops = 2,
): Set<string> {
  const adj = buildAdjacency(edges);
  const result = new Set<string>();
  let frontier = [...seedIds];

  for (const id of seedIds) result.add(id);

  for (let h = 0; h < hops; h++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of adj.get(id) ?? []) {
        if (!result.has(nb)) {
          result.add(nb);
          next.push(nb);
        }
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return result;
}

export function getNeighbors(
  edges: GraphEdge[],
  nodeId: string,
): { id: string; direction: "in" | "out" }[] {
  const out: { id: string; direction: "in" | "out" }[] = [];
  for (const e of edges) {
    if (e.from === nodeId) out.push({ id: e.to, direction: "out" });
    if (e.to === nodeId) out.push({ id: e.from, direction: "in" });
  }
  return out;
}
