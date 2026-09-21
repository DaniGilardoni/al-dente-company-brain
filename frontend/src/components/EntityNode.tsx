import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { EntityNodeData, NodeGroup } from "../types/graph";

const GROUP_COLOR: Record<NodeGroup, string> = {
  customer: "#38bdf8",
  product: "#34d399",
  material: "#fbbf24",
  supplier: "#c084fc",
  document: "#fb7185",
};

/** Compact graph dot — label appears on hover / highlight / select. */
export function EntityNode({ data, selected }: NodeProps) {
  const d = data as unknown as EntityNodeData;
  const color = GROUP_COLOR[d.group] ?? "#71717a";
  const active = d.highlighted || d.hovered || selected;
  const faded = d.dimmed && !active;

  return (
    <>
      <Handle type="target" position={Position.Top} className="!opacity-0 !h-px !w-px !min-h-0 !min-w-0 !border-0" />
      <div
        className="relative flex flex-col items-center"
        style={{ width: 12, height: active ? 36 : 12 }}
      >
        <div
          className={[
            "rounded-full border transition-all duration-200",
            active
              ? "border-slate-900/70 shadow-[0_0_12px_currentColor]"
              : "border-black/25",
            selected ? "scale-150" : active ? "scale-125" : "scale-100",
            faded ? "opacity-30" : "opacity-100",
          ].join(" ")}
          style={{
            width: d.highlighted || selected ? 14 : 10,
            height: d.highlighted || selected ? 14 : 10,
            backgroundColor: color,
            color: color,
          }}
          title={`${d.label} (${d.nodeId})`}
        />
        {active && (
          <span
            className={[
              "pointer-events-none absolute top-4 max-w-[100px] truncate rounded px-1 py-0.5 text-center font-mono text-[8px] leading-tight",
              d.highlighted || selected
                ? "bg-teal-600 text-white ring-1 ring-teal-500/40"
                : "bg-white/90 text-slate-700 ring-1 ring-slate-200",
            ].join(" ")}
          >
            {d.nodeId}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0 !h-px !w-px !min-h-0 !min-w-0 !border-0" />
    </>
  );
}

export const entityNodeTypes = { entity: EntityNode };
