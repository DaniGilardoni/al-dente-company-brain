import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Factory,
  Phone,
  Search,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { TOOL_COLOR, TOOL_GROUPS, TOOL_META } from "../lib/orchestration";
import type { ToolId, ToolState } from "../types/ask";
import type { GraphNode } from "../types/graph";

const ICONS: Record<ToolId, typeof Users> = {
  crm: Users,
  erp: Factory,
  kb: BookOpen,
  calls: Phone,
};

interface OrchestrationHubProps {
  tools: ToolState[];
  loading: boolean;
  activeId: ToolId | null;
  onSelect: (id: ToolId) => void;
  nodes: GraphNode[];
  focusId: string | null;
  onFocusNode: (id: string | null) => void;
}

export function OrchestrationHub({
  tools,
  loading,
  activeId,
  onSelect,
  nodes,
  focusId,
  onFocusNode,
}: OrchestrationHubProps) {
  const [filter, setFilter] = useState("");

  // Reset the text filter whenever the selected tool changes.
  useEffect(() => {
    setFilter("");
  }, [activeId]);

  // Nodes belonging to the selected tool's groups, narrowed by the text filter.
  const items = useMemo(() => {
    if (!activeId) return [];
    const groups = TOOL_GROUPS[activeId];
    const base = nodes.filter((n) => groups.includes(n.group));
    const q = filter.trim().toLowerCase();
    if (!q) return base;
    return base.filter(
      (n) =>
        n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q),
    );
  }, [activeId, nodes, filter]);

  const totalForTool = useMemo(() => {
    if (!activeId) return 0;
    const groups = TOOL_GROUPS[activeId];
    return nodes.filter((n) => groups.includes(n.group)).length;
  }, [activeId, nodes]);

  return (
    <aside className="glass flex w-56 shrink-0 flex-col border-r border-slate-200/70 bg-white/30 lg:w-60">
      <div className="border-b border-slate-200/70 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Intelligence Orchestration
        </h2>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3">
        {tools.map((tool) => {
          const meta = TOOL_META[tool.id];
          const Icon = ICONS[tool.id];
          const active = tool.status === "active";
          const used = tool.status === "used";
          const selected = tool.id === activeId;
          const color = TOOL_COLOR[tool.id];
          const accent = active || used || selected;

          return (
            <div key={tool.id} className="flex flex-col">
              <motion.button
                type="button"
                onClick={() => onSelect(tool.id)}
                aria-pressed={selected}
                animate={
                  active
                    ? { boxShadow: [`0 0 0 0 ${color}00`, `0 0 0 4px ${color}33`, `0 0 0 0 ${color}00`] }
                    : {}
                }
                transition={active ? { repeat: Infinity, duration: 1.6 } : {}}
                style={
                  selected
                    ? {
                        borderColor: color,
                        backgroundColor: `${color}1f`,
                        boxShadow: `0 0 0 2px ${color}66`,
                      }
                    : undefined
                }
                className={`w-full cursor-pointer rounded-xl border p-3 text-left transition hover:border-slate-300 hover:bg-white/70 ${
                  selected
                    ? ""
                    : active
                      ? "bg-white/60"
                      : used
                        ? "border-slate-200 bg-white/60"
                        : "border-slate-200 bg-white/50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div
                      className="rounded-lg p-1.5"
                      style={{
                        backgroundColor: `${color}${accent ? "26" : "1a"}`,
                        color,
                        opacity: accent ? 1 : 0.7,
                      }}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">{meta.label}</p>
                      <p className="text-[10px] text-slate-400">{meta.subtitle}</p>
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase ${
                      accent ? "" : "bg-slate-200 text-slate-500"
                    }`}
                    style={accent ? { backgroundColor: `${color}26`, color } : undefined}
                  >
                    {active ? "Active" : used ? "Used" : selected ? "Filter" : "Idle"}
                  </span>
                </div>
                {tool.evidenceCount > 0 && (
                  <p className="mt-2 text-[10px] text-slate-400">
                    {tool.evidenceCount} source{tool.evidenceCount !== 1 ? "s" : ""}
                  </p>
                )}
              </motion.button>

              <AnimatePresence initial={false}>
                {selected && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div
                      className="mt-1.5 rounded-xl border bg-white/60 p-2"
                      style={{ borderColor: `${TOOL_COLOR[tool.id]}66` }}
                    >
                      <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1">
                        <Search className="h-3 w-3 shrink-0 text-slate-400" />
                        <input
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                          placeholder={`Filter ${meta.label}…`}
                          className="w-full bg-transparent text-[11px] text-slate-700 outline-none placeholder:text-slate-400"
                          autoFocus
                        />
                      </div>

                      <p className="mt-1.5 px-1 text-[10px] text-slate-400">
                        {items.length} of {totalForTool}
                      </p>

                      <ul className="mt-1 flex max-h-56 flex-col gap-0.5 overflow-y-auto">
                        {items.map((n) => {
                          const isFocus = n.id.toUpperCase() === focusId?.toUpperCase();
                          return (
                            <li key={n.id}>
                              <button
                                type="button"
                                onClick={() => onFocusNode(isFocus ? null : n.id)}
                                title={n.title ?? n.label}
                                style={
                                  isFocus
                                    ? { backgroundColor: `${TOOL_COLOR[tool.id]}2e` }
                                    : undefined
                                }
                                className={`flex w-full items-center gap-1.5 truncate rounded-md px-2 py-1 text-left text-[11px] transition ${
                                  isFocus
                                    ? "font-medium text-slate-800"
                                    : "text-slate-600 hover:bg-slate-100"
                                }`}
                              >
                                <span
                                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                                  style={{ backgroundColor: TOOL_COLOR[tool.id] }}
                                />
                                <span className="truncate">{n.label}</span>
                              </button>
                            </li>
                          );
                        })}
                        {items.length === 0 && (
                          <li className="px-2 py-2 text-[10px] text-slate-400">
                            No matches
                          </li>
                        )}
                      </ul>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
      {loading && (
        <div className="border-t border-slate-200/70 px-4 py-2 text-[11px] text-teal-600">
          Orchestrating tools…
        </div>
      )}
    </aside>
  );
}
