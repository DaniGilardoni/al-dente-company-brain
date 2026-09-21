import { useCallback, useMemo, useRef, useState } from "react";
import { CommandBar } from "./components/CommandBar";
import { ExecutiveMemo } from "./components/ExecutiveMemo";
import { Header } from "./components/Header";
import { KnowledgeGraph } from "./components/KnowledgeGraph";
import { OrchestrationHub } from "./components/OrchestrationHub";
import { useAsk } from "./hooks/useAsk";
import { useGraph } from "./hooks/useGraph";
import { extractEntityIds } from "./lib/extractIds";
import { buildToolStates, TOOL_GROUPS } from "./lib/orchestration";
import type { ToolId } from "./types/ask";
import type { NodeGroup } from "./types/graph";

function guessVerticale(question: string): "crm" | "erp" | "calls" | "kb" {
  const q = question.toLowerCase();
  if (q.includes("call") || q.includes("complaint") || q.includes("phone")) return "calls";
  if (q.includes("lot") || q.includes("inventory") || q.includes("stock") || q.includes("bom")) return "erp";
  if (q.includes("opportunit") || q.includes("customer") || q.includes("order") || q.includes("invoice")) return "crm";
  return "kb";
}

const SUGGESTIONS: { label: string; question: string }[] = [
  {
    label: "Open deals for Primato",
    question:
      "How many open opportunities does Primato Supermercati S.p.A. (CUST-0132) have, and what is their total value?",
  },
  {
    label: "PAS-PEN-500 below min stock?",
    question:
      "Is SKU PAS-PEN-500 (Penne Rigate n.73 - 500g box) below its minimum stock? Give the on-hand quantity.",
  },
  {
    label: "Shelf life & allergens (PAS-SPA-500)",
    question:
      "What is the shelf life (TMC) and the declared allergens for Spaghetti n.5 - 500g box (SKU PAS-SPA-500)?",
  },
  {
    label: "Count 'broken pasta' complaints",
    question:
      "Across ALL recorded calls, count how many quality complaints concern the defect 'broken pasta'. Give the exact number.",
  },
  {
    label: "Generate a sales deck",
    question:
      "Generate a 4-slide HTML deck for the sales rep visiting Primato Supermercati S.p.A. (CUST-0132): profile, open deals, order/lot status, recent call complaints.",
  },
];

export default function App() {
  const { ask, newChat, restore, history, loading, thread } = useAsk();
  const { data: graphData, loading: graphLoading, error: graphError } = useGraph();
  const [focusId, setFocusId] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<ToolId | null>(null);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);
  const prefillNonce = useRef(0);

  // Focus a node in the graph and seed the chat with its reference so the
  // user can ask about it directly.
  const handleFocusNode = useCallback(
    (id: string | null) => {
      setFocusId(id);
      if (!id) return;
      const node = graphData?.nodes.find(
        (n) => n.id.toUpperCase() === id.toUpperCase(),
      );
      const ref =
        node && node.label !== node.id ? `${node.label} (${node.id})` : id;
      prefillNonce.current += 1;
      setPrefill({ text: `${ref} `, nonce: prefillNonce.current });
    },
    [graphData],
  );

  const activeGroups = useMemo<Set<NodeGroup> | null>(
    () => (activeTool ? new Set(TOOL_GROUPS[activeTool]) : null),
    [activeTool],
  );

  const handleToolSelect = useCallback((id: ToolId) => {
    setActiveTool((cur) => (cur === id ? null : id));
    setFocusId(null);
  }, []);

  // Graph + orchestration reflect the most recent answered turn.
  const latest = useMemo(
    () => [...thread].reverse().find((t) => t.answer)?.answer ?? null,
    [thread],
  );
  const lastQuestion = thread.length ? thread[thread.length - 1].question : null;

  const highlightIds = useMemo(() => {
    const ids = new Set<string>();
    if (focusId) ids.add(focusId.toUpperCase());
    if (latest) {
      for (const id of extractEntityIds(latest.answer)) ids.add(id);
      for (const s of latest.sources) {
        if (/^[A-Z]+-\d+/i.test(s)) ids.add(s.toUpperCase());
      }
    }
    return ids;
  }, [latest, focusId]);

  const toolStates = useMemo(() => {
    if (loading && lastQuestion) {
      return buildToolStates([], guessVerticale(lastQuestion), true);
    }
    return buildToolStates(latest?.sources ?? [], null, false);
  }, [loading, latest, lastQuestion]);

  const handleAsk = useCallback(
    async (question: string) => {
      setFocusId(null);
      setActiveTool(null);
      await ask(question);
    },
    [ask],
  );

  const handleClose = useCallback(() => {
    newChat();
    setFocusId(null);
    setActiveTool(null);
  }, [newChat]);

  return (
    <div className="app-backdrop flex h-screen flex-col overflow-hidden text-slate-700">
      <Header />

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <OrchestrationHub
          tools={toolStates}
          loading={loading}
          activeId={activeTool}
          onSelect={handleToolSelect}
          nodes={graphData?.nodes ?? []}
          focusId={focusId}
          onFocusNode={handleFocusNode}
        />

        <KnowledgeGraph
          data={graphData}
          loading={graphLoading}
          error={graphError}
          highlightIds={highlightIds}
          activeGroups={activeGroups}
          scanning={loading}
          xray={false}
          focusId={focusId}
          onFocusNode={handleFocusNode}
        />

        <ExecutiveMemo
          thread={thread}
          loading={loading}
          suggestions={SUGGESTIONS}
          history={history}
          onAsk={handleAsk}
          onHighlight={setFocusId}
          onClose={handleClose}
          onRestore={restore}
        />
      </div>

      <CommandBar
        onSubmit={handleAsk}
        loading={loading}
        prefill={prefill}
        conversing={thread.length > 0}
      />
    </div>
  );
}
