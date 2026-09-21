import { X } from "lucide-react";
import type { GraphData, GraphNode } from "../types/graph";
import { getNeighbors } from "../lib/forceLayout";

interface NodeInspectorProps {
  node: GraphNode;
  data: GraphData;
  onClose: () => void;
  onNavigate: (id: string) => void;
}

export function NodeInspector({ node, data, onClose, onNavigate }: NodeInspectorProps) {
  const neighbors = getNeighbors(data.edges, node.id);

  return (
    <div className="absolute bottom-4 left-4 z-30 w-72 rounded-xl border border-slate-200 bg-white/90 p-4 shadow-2xl backdrop-blur-md">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-teal-700">
            {node.group}
          </p>
          <h3 className="mt-0.5 text-sm font-semibold text-slate-900">{node.label}</h3>
          <p className="font-mono text-[10px] text-slate-400">{node.id}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-900"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {node.title && node.title !== node.label && (
        <p className="mb-3 text-xs leading-relaxed text-slate-500">{node.title}</p>
      )}

      {neighbors.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-400">
            Connected ({neighbors.length})
          </p>
          <div className="max-h-36 space-y-1 overflow-y-auto">
            {neighbors.map(({ id, direction }) => {
              const nb = data.nodes.find((n) => n.id === id);
              return (
                <button
                  key={`${direction}-${id}`}
                  type="button"
                  onClick={() => onNavigate(id)}
                  className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white/60 px-2 py-1.5 text-left transition hover:border-teal-500/30 hover:bg-teal-500/10"
                >
                  <span className="text-[10px] text-slate-400">{direction === "out" ? "→" : "←"}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-slate-600">
                    {nb?.label ?? id}
                  </span>
                  <span className="font-mono text-[9px] text-slate-400">{id}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
