import type { ToolId, ToolState, Verticale } from "../types/ask";
import type { NodeGroup } from "../types/graph";

/** Which graph node groups each tool/vertical lights up. */
export const TOOL_GROUPS: Record<ToolId, NodeGroup[]> = {
  crm: ["customer"],
  erp: ["product", "material", "supplier"],
  kb: ["document"],
  calls: ["customer"], // transcripts are tied to customers; no call nodes in graph
};

/** Node colors used across the graph and the orchestration panel. */
export const GROUP_COLORS: Record<NodeGroup, string> = {
  customer: "#38bdf8",
  product: "#34d399",
  material: "#fbbf24",
  supplier: "#c084fc",
  document: "#fb7185",
};

/** Each tool inherits the color of its primary graph group. */
export const TOOL_COLOR: Record<ToolId, string> = {
  crm: GROUP_COLORS.customer,
  erp: GROUP_COLORS.product,
  kb: GROUP_COLORS.document,
  calls: GROUP_COLORS.customer,
};

const TOOL_PREFIX: Record<ToolId, string[]> = {
  crm: ["crm/"],
  erp: ["erp/"],
  calls: ["calls/"],
  kb: ["DOC-", "kb/"],
};

function sourceMatchesTool(source: string, tool: ToolId): boolean {
  const prefixes = TOOL_PREFIX[tool];
  return prefixes.some((p) => source.startsWith(p) || source.includes(p));
}

export function buildToolStates(
  sources: string[],
  activeVerticale: Verticale | null,
  loading: boolean,
): ToolState[] {
  const tools: ToolId[] = ["crm", "erp", "kb", "calls"];

  return tools.map((id) => {
    const evidenceCount = sources.filter((s) => sourceMatchesTool(s, id)).length;
    let status: ToolState["status"] = "idle";

    if (loading && activeVerticale === id) {
      status = "active";
    } else if (evidenceCount > 0) {
      status = "used";
    }

    return { id, status, evidenceCount };
  });
}

export const TOOL_META: Record<
  ToolId,
  { label: string; subtitle: string }
> = {
  crm: { label: "CRM", subtitle: "Customers & deals" },
  erp: { label: "ERP", subtitle: "Inventory & BOM" },
  kb: { label: "RAG", subtitle: "Knowledge base" },
  calls: { label: "Call Logs", subtitle: "Transcripts" },
};
