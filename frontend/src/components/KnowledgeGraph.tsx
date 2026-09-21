import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { GraphData, GraphNode, NodeGroup } from "../types/graph";
import type { EntityNodeData } from "../types/graph";
import {
  computeForceLayoutWithMeta,
  expandNeighborhood,
} from "../lib/forceLayout";
import { entityNodeTypes } from "./EntityNode";
import { NodeInspector } from "./NodeInspector";
import { GROUP_COLORS } from "../lib/orchestration";

interface KnowledgeGraphProps {
  data: GraphData | null;
  loading: boolean;
  error: string | null;
  highlightIds: Set<string>;
  activeGroups: Set<NodeGroup> | null;
  scanning: boolean;
  xray: boolean;
  focusId: string | null;
  onFocusNode: (id: string | null) => void;
}

function FitViewController({
  highlightIds,
  focusId,
  layoutReady,
  coreNodeIds,
}: {
  highlightIds: Set<string>;
  focusId: string | null;
  layoutReady: boolean;
  coreNodeIds: Set<string>;
}) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    if (!layoutReady) return;

    if (focusId) {
      fitView({ nodes: [{ id: focusId }], padding: 0.5, duration: 600, maxZoom: 1.8 });
      return;
    }

    if (highlightIds.size > 0) {
      fitView({
        nodes: [...highlightIds].map((id) => ({ id })),
        padding: 0.35,
        duration: 800,
        maxZoom: 1.4,
      });
      return;
    }

    fitView({
      nodes: [...coreNodeIds].map((id) => ({ id })),
      padding: 0.18,
      duration: 500,
      maxZoom: 1.6,
    });
  }, [highlightIds, focusId, layoutReady, fitView, coreNodeIds]);

  return null;
}

function GraphCanvas({
  data,
  loading,
  error,
  highlightIds,
  activeGroups,
  scanning,
  xray,
  focusId,
  onFocusNode,
}: KnowledgeGraphProps) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [layoutReady, setLayoutReady] = useState(false);

  const { positions, coreIds: coreNodeIds } = useMemo(() => {
    if (!data) return { positions: new Map<string, { x: number; y: number }>(), coreIds: new Set<string>() };
    setLayoutReady(false);
    return computeForceLayoutWithMeta(data);
  }, [data]);

  useEffect(() => {
    if (positions.size > 0) {
      const t = setTimeout(() => setLayoutReady(true), 50);
      return () => clearTimeout(t);
    }
  }, [positions]);

  const connectionCounts = useMemo(() => {
    const counts = new Map<string, number>();
    if (!data) return counts;
    for (const e of data.edges) {
      counts.set(e.from, (counts.get(e.from) ?? 0) + 1);
      counts.set(e.to, (counts.get(e.to) ?? 0) + 1);
    }
    return counts;
  }, [data]);

  const activeHighlights = useMemo(() => {
    if (!data || highlightIds.size === 0) return highlightIds;
    return expandNeighborhood(data.edges, highlightIds, 2);
  }, [data, highlightIds]);

  const hoverNeighborhood = useMemo(() => {
    if (!hoveredId || !data) return new Set<string>();
    return expandNeighborhood(data.edges, new Set([hoveredId]), 1);
  }, [hoveredId, data]);

  // Nodes lit by the current filter. A picked node (focusId) wins and lights
  // only itself; otherwise: answer entities (neighborhood-expanded) plus all
  // nodes belonging to a selected tool's groups.
  const litIds = useMemo(() => {
    if (focusId) {
      return new Set<string>([focusId, focusId.toUpperCase()]);
    }
    const s = new Set<string>(activeHighlights);
    if (data && activeGroups && activeGroups.size > 0) {
      for (const n of data.nodes) {
        if (activeGroups.has(n.group)) s.add(n.id);
      }
    }
    return s;
  }, [focusId, activeHighlights, activeGroups, data]);

  const nodes: Node[] = useMemo(() => {
    if (!data) return [];

    return data.nodes.map((n) => {
      const highlighted =
        litIds.has(n.id) ||
        litIds.has(n.id.toUpperCase()) ||
        n.id.toUpperCase() === focusId?.toUpperCase();
      const hovered = hoverNeighborhood.has(n.id) || hoveredId === n.id;
      const dimmed =
        !xray &&
        litIds.size > 0 &&
        !highlighted &&
        !hovered &&
        selectedNode?.id !== n.id;

      const nodeData: EntityNodeData = {
        label: n.label,
        nodeId: n.id,
        group: n.group,
        title: n.title ?? n.label,
        highlighted,
        dimmed,
        hovered,
        connectionCount: connectionCounts.get(n.id) ?? 0,
      };

      return {
        id: n.id,
        type: "entity",
        position: positions.get(n.id) ?? { x: 0, y: 0 },
        data: nodeData,
        draggable: true,
      };
    });
  }, [
    data,
    positions,
    litIds,
    focusId,
    hoverNeighborhood,
    hoveredId,
    xray,
    selectedNode,
    connectionCounts,
  ]);

  const edges: Edge[] = useMemo(() => {
    if (!data) return [];

    return data.edges.map((e, i) => {
      const pathLit = litIds.has(e.from) && litIds.has(e.to);
      const hoverLit =
        hoveredId &&
        (e.from === hoveredId || e.to === hoveredId);

      return {
        id: `e-${i}`,
        source: e.from,
        target: e.to,
        type: "straight",
        animated: pathLit || !!hoverLit,
        style: {
          stroke: pathLit ? "#0d9488" : hoverLit ? "#0ea5a3" : "#94a3b8",
          strokeWidth: pathLit ? 2 : hoverLit ? 1.6 : 1,
          opacity:
            litIds.size > 0 && !pathLit && !hoverLit && !xray
              ? 0.18
              : pathLit ? 0.95 : 0.6,
        },
      };
    });
  }, [data, litIds, hoveredId, xray]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const gn = data?.nodes.find((n) => n.id === node.id);
      if (gn) {
        setSelectedNode(gn);
        onFocusNode(node.id);
      }
    },
    [data, onFocusNode],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    onFocusNode(null);
  }, [onFocusNode]);

  const stats = useMemo(() => {
    if (!data) return null;
    return {
      nodes: data.nodes.length,
      edges: data.edges.length,
    };
  }, [data]);

  return (
    <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-4 py-2">
        <div className="flex items-center gap-3">
          <h2 className="whitespace-nowrap text-xs font-semibold uppercase tracking-widest text-slate-500">
            Living Knowledge Graph
          </h2>
          {stats && (
            <span className="rounded-full border border-slate-200 bg-white/60 px-2 py-0.5 text-[10px] text-slate-500">
              {stats.nodes} nodes · {stats.edges} links
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5 text-[10px] text-slate-500">
          {(
            ["customer", "product", "material", "supplier", "document"] as NodeGroup[]
          ).map((g) => (
            <span
              key={g}
              className="flex items-center gap-1 rounded-full border border-slate-200 bg-white/60 px-2 py-0.5 capitalize"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: GROUP_COLORS[g], boxShadow: `0 0 6px ${GROUP_COLORS[g]}` }}
              />
              {g}
            </span>
          ))}
        </div>
      </div>

      <div className="relative flex-1 overflow-hidden bg-[radial-gradient(circle_at_50%_38%,#f6f9f8,#e3eae7)]">
        {!scanning && !loading && (
          <div className="pointer-events-none absolute left-1/2 top-1/2 z-20 h-[440px] w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(13,148,136,0.10),transparent_70%)] blur-3xl animate-breathe" />
        )}

        {scanning && (
          <motion.div
            initial={{ top: "-10%" }}
            animate={{ top: "110%" }}
            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
            className="pointer-events-none absolute inset-x-0 z-10 h-24 bg-gradient-to-b from-transparent via-teal-500/20 to-transparent"
          />
        )}

        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/50 text-sm text-slate-500">
            Building knowledge graph…
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-20 flex items-center justify-center p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        {data && !loading && layoutReady && (
          <>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={entityNodeTypes}
              onNodeClick={onNodeClick}
              onNodeMouseEnter={(_, n) => setHoveredId(n.id)}
              onNodeMouseLeave={() => setHoveredId(null)}
              onPaneClick={onPaneClick}
              minZoom={0.05}
              maxZoom={3}
              nodesDraggable
              nodesConnectable={false}
              proOptions={{ hideAttribution: true }}
              className="!bg-transparent"
            >
              <FitViewController
                highlightIds={litIds}
                focusId={focusId}
                layoutReady={layoutReady}
                coreNodeIds={coreNodeIds}
              />
              <Background
                variant={BackgroundVariant.Dots}
                gap={26}
                size={1}
                color="#c2cdc8"
              />
            </ReactFlow>

            {selectedNode && (
              <NodeInspector
                node={selectedNode}
                data={data}
                onClose={() => {
                  setSelectedNode(null);
                  onFocusNode(null);
                }}
                onNavigate={(id) => {
                  const gn = data.nodes.find((n) => n.id === id);
                  if (gn) {
                    setSelectedNode(gn);
                    onFocusNode(id);
                  }
                }}
              />
            )}

            <p className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-slate-300/70 bg-white/70 px-3 py-1 text-[10px] text-slate-500 backdrop-blur-sm">
              Click a node to explore · drag to rearrange · scroll to zoom
            </p>
          </>
        )}
      </div>
    </main>
  );
}

export function KnowledgeGraph(props: KnowledgeGraphProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
