import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  Expand,
  FileText,
  History,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  extractEntityIds,
  inferConfidence,
  isHtmlAnswer,
} from "../lib/extractIds";
import type { AskResponse, HistoryItem, Turn } from "../types/ask";

interface Suggestion {
  label: string;
  question: string;
}

interface ExecutiveMemoProps {
  thread: Turn[];
  loading: boolean;
  suggestions: Suggestion[];
  history: HistoryItem[];
  onAsk: (question: string) => void;
  onHighlight: (id: string) => void;
  onClose: () => void;
  onRestore: (item: HistoryItem) => void;
}

const VERTICALE_LABEL: Record<string, string> = {
  crm: "CRM",
  erp: "ERP",
  calls: "Call Logs",
  kb: "Knowledge Base",
};

type ArtifactKind = "pdf" | "image" | "office" | "other";

const ARTIFACT_KIND_LABEL: Record<ArtifactKind, string> = {
  pdf: "PDF document",
  image: "Image",
  office: "Office document",
  other: "File",
};

/** What the fullscreen modal is currently showing. */
type ExpandTarget =
  | { kind: "html"; html: string }
  | { kind: "file"; url: string; fileType: ArtifactKind; name: string };

function artifactKind(url: string): ArtifactKind {
  const clean = url.split(/[?#]/)[0].toLowerCase();
  if (clean.endsWith(".pdf")) return "pdf";
  if (/\.(png|jpe?g|gif|webp|svg|bmp|avif)$/.test(clean)) return "image";
  if (/\.(docx?|pptx?|xlsx?|csv)$/.test(clean)) return "office";
  return "other";
}

function artifactFileName(url: string): string {
  const clean = url.split(/[?#]/)[0];
  try {
    return decodeURIComponent(clean.split("/").pop() || "") || "artifact";
  } catch {
    return clean.split("/").pop() || "artifact";
  }
}

function isLocalUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "0.0.0.0" ||
      host.endsWith(".local")
    );
  } catch {
    return false;
  }
}

function ArtifactFallback({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-[10rem] flex-col items-center justify-center gap-2 p-6 text-center text-slate-400">
      <FileText className="h-8 w-8" />
      <p className="max-w-xs text-xs leading-relaxed">{message}</p>
    </div>
  );
}

/** Renders the actual artifact content inline (compact) or full-height (modal). */
function ArtifactEmbed({
  url,
  kind,
  full = false,
}: {
  url: string;
  kind: ArtifactKind;
  full?: boolean;
}) {
  if (kind === "image") {
    return (
      <div className={`flex items-center justify-center ${full ? "h-full" : "p-2"}`}>
        <img
          src={url}
          alt="Artifact preview"
          className={`w-auto object-contain ${full ? "max-h-full" : "max-h-72"}`}
        />
      </div>
    );
  }

  if (kind === "pdf") {
    return (
      <iframe
        title="Artifact preview"
        src={`${url}#toolbar=1&view=FitH`}
        className={`w-full border-0 bg-white ${full ? "h-full" : "h-72"}`}
      />
    );
  }

  if (kind === "office") {
    if (isLocalUrl(url)) {
      return (
        <ArtifactFallback message="Inline preview for Office files needs a public URL. Use Open to download it." />
      );
    }
    const viewer = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(url)}`;
    return (
      <iframe
        title="Artifact preview"
        src={viewer}
        className={`w-full border-0 bg-white ${full ? "h-full" : "h-72"}`}
      />
    );
  }

  return (
    <ArtifactFallback message="Inline preview is not available for this file type. Use Open to download it." />
  );
}

/** The artifact card shown inside an answer: header actions + inline preview. */
function ArtifactCard({
  url,
  onExpand,
}: {
  url: string;
  onExpand: (target: ExpandTarget) => void;
}) {
  const kind = artifactKind(url);
  const name = artifactFileName(url);

  return (
    <div className="overflow-hidden rounded-xl border border-teal-500/30 bg-teal-500/[0.07]">
      <div className="flex items-center gap-2 px-3 py-2">
        <FileText className="h-4 w-4 shrink-0 text-teal-600" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-teal-700">{name}</p>
          <p className="truncate text-[10px] text-slate-400">{ARTIFACT_KIND_LABEL[kind]}</p>
        </div>
        <button
          type="button"
          onClick={() => onExpand({ kind: "file", url, fileType: kind, name })}
          className="flex items-center gap-1 rounded-md border border-teal-500/30 bg-white/70 px-2 py-1 text-[10px] text-teal-700 transition hover:border-teal-400/60 hover:bg-white"
        >
          <Expand className="h-3 w-3" />
          Expand
        </button>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 rounded-md border border-teal-500/30 bg-white/70 px-2 py-1 text-[10px] text-teal-700 transition hover:border-teal-400/60 hover:bg-white"
        >
          <Download className="h-3 w-3" />
          Open
        </a>
      </div>
      <div className="border-t border-teal-500/20 bg-white">
        <ArtifactEmbed url={url} kind={kind} />
      </div>
    </div>
  );
}

function AnswerBlock({
  answer,
  onHighlight,
  onExpand,
}: {
  answer: AskResponse;
  onHighlight: (id: string) => void;
  onExpand: (target: ExpandTarget) => void;
}) {
  const [copied, setCopied] = useState(false);
  const confidence = inferConfidence(answer.answer, answer.sources);
  const html = isHtmlAnswer(answer.answer);
  const evidenceIds = [...new Set(extractEntityIds(answer.answer))];

  const copyAnswer = () => {
    navigator.clipboard?.writeText(answer.answer).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="space-y-3">
      {confidence && (
        <div>
          <div className="mb-1 flex justify-between text-[10px] text-slate-400">
            <span className="uppercase tracking-wider">Confidence</span>
            <span>{confidence.label}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${confidence.value}%` }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="h-full rounded-full bg-gradient-to-r from-teal-600 to-emerald-400"
            />
          </div>
        </div>
      )}

      <div className="relative rounded-xl border border-slate-200 bg-white/60 p-3">
        <div className="absolute right-2 top-2 z-10 flex items-center gap-1">
          {html && (
            <button
              type="button"
              onClick={() => onExpand({ kind: "html", html: answer.answer })}
              className="flex items-center gap-1 rounded-md border border-slate-200 bg-white/80 px-2 py-1 text-[10px] text-slate-600 backdrop-blur transition hover:border-teal-500/40 hover:text-teal-700"
            >
              <Expand className="h-3 w-3" />
              Expand
            </button>
          )}
          <button
            type="button"
            onClick={copyAnswer}
            className="flex items-center gap-1 rounded-md border border-slate-200 bg-white/80 px-2 py-1 text-[10px] text-slate-600 backdrop-blur transition hover:border-teal-500/40 hover:text-teal-700"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        {html ? (
          <div
            className="answer-html max-h-72 overflow-hidden"
            dangerouslySetInnerHTML={{ __html: answer.answer }}
          />
        ) : (
          <p className="whitespace-pre-wrap pr-12 text-sm leading-relaxed text-slate-700">
            {answer.answer}
          </p>
        )}
        {html && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 rounded-b-xl bg-gradient-to-t from-white to-transparent" />
        )}
      </div>

      {evidenceIds.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-wider text-slate-400">
            Evidence · click to trace in graph
          </p>
          <div className="flex flex-wrap gap-1.5">
            {evidenceIds.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => onHighlight(id)}
                className="group flex items-center gap-1 rounded-md border border-teal-500/30 bg-teal-500/10 px-2 py-0.5 font-mono text-[11px] text-teal-700 transition hover:border-teal-400/60 hover:bg-teal-500/20"
              >
                {id}
                <ArrowUpRight className="h-2.5 w-2.5 opacity-0 transition group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-slate-400">Sources</p>
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700">
            {VERTICALE_LABEL[answer.verticale] ?? answer.verticale}
          </span>
          {answer.sources.map((s) => (
            <span
              key={s}
              className="rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500"
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      {answer.artifact_url && (
        <ArtifactCard url={answer.artifact_url} onExpand={onExpand} />
      )}
    </div>
  );
}

export function ExecutiveMemo({
  thread,
  loading,
  suggestions,
  history,
  onAsk,
  onHighlight,
  onClose,
  onRestore,
}: ExecutiveMemoProps) {
  const [expanded, setExpanded] = useState<ExpandTarget | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Keep the latest turn in view as the conversation grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread, loading]);

  // Drive native (whole-screen) fullscreen alongside the artifact modal.
  useEffect(() => {
    if (expanded) {
      modalRef.current?.requestFullscreen?.().catch(() => {});
    } else if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    }
  }, [expanded]);

  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement) setExpanded(null);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const empty = thread.length === 0 && !loading;

  return (
    <aside className="glass flex w-72 shrink-0 flex-col border-l border-slate-200/70 bg-white/30 lg:w-80 xl:w-96">
      <div className="flex items-center justify-between border-b border-slate-200/70 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Executive Memo
        </h2>
        {thread.length > 0 && (
          <button
            type="button"
            onClick={onClose}
            title="New chat"
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[10px] text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <Plus className="h-3 w-3" />
            New chat
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        {thread.map((turn) => (
          <div key={turn.id} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[88%] rounded-2xl rounded-tr-sm border border-teal-500/20 bg-teal-500/10 px-3 py-2 text-sm text-slate-700">
                {turn.question}
              </p>
            </div>

            {turn.answer && (
              <AnswerBlock
                answer={turn.answer}
                onHighlight={onHighlight}
                onExpand={setExpanded}
              />
            )}

            {turn.error && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700">
                {turn.error}
              </div>
            )}

            {!turn.answer && !turn.error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                <div className="h-2 w-3/4 animate-pulse rounded bg-teal-500/20" />
                <div className="h-2 w-full animate-pulse rounded bg-slate-200" />
                <div className="h-2 w-5/6 animate-pulse rounded bg-slate-200" />
                <div className="h-2 w-2/3 animate-pulse rounded bg-slate-200" />
                <p className="flex items-center gap-1.5 pt-2 text-xs italic text-teal-600">
                  <Sparkles className="h-3.5 w-3.5 animate-pulse" />
                  Routing tools & analyzing company data…
                </p>
              </motion.div>
            )}
          </div>
        ))}

        {empty && (
          <div className="space-y-4">
            <p className="text-sm leading-relaxed text-slate-500">
              Ask anything about Al Dente S.r.l. The brain routes across{" "}
              <span className="text-teal-700">CRM</span>,{" "}
              <span className="text-teal-700">ERP</span>,{" "}
              <span className="text-teal-700">call logs</span> and the{" "}
              <span className="text-teal-700">knowledge base</span>, then traces the
              evidence in the graph. Follow-up questions continue the same chat.
            </p>
            <div>
              <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-400">
                Start with
              </p>
              <div className="space-y-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    onClick={() => onAsk(s.question)}
                    className="group flex w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white/50 px-3 py-2 text-left transition hover:border-teal-500/30 hover:bg-teal-500/[0.07]"
                  >
                    <span className="text-xs text-slate-600 group-hover:text-teal-700">
                      {s.label}
                    </span>
                    <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-slate-400 transition group-hover:text-teal-600" />
                  </button>
                ))}
              </div>
            </div>

            {history.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setHistoryOpen((v) => !v)}
                  className="mb-2 flex w-full items-center gap-1 text-[10px] uppercase tracking-wider text-slate-400 transition hover:text-slate-600"
                >
                  <History className="h-3 w-3" />
                  Past chats
                  <span className="font-mono text-slate-300">({history.length})</span>
                  {historyOpen ? (
                    <ChevronDown className="ml-auto h-3 w-3" />
                  ) : (
                    <ChevronRight className="ml-auto h-3 w-3" />
                  )}
                </button>
                {historyOpen && (
                <div className="space-y-1.5">
                  {[...history].reverse().map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onRestore(item)}
                      className="group flex w-full items-start justify-between gap-2 rounded-lg border border-slate-200 bg-white/50 px-3 py-2 text-left transition hover:border-teal-500/30 hover:bg-teal-500/[0.07]"
                    >
                      <span className="line-clamp-2 text-xs text-slate-600 group-hover:text-teal-700">
                        {item.question}
                      </span>
                      <span className="shrink-0 pt-0.5 font-mono text-[9px] text-slate-400">
                        {item.turns.length}t ·{" "}
                        {new Date(item.at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </button>
                  ))}
                </div>
                )}
              </div>
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            ref={modalRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-white backdrop-blur-sm"
            onClick={() => setExpanded(null)}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="relative flex h-full w-full flex-col overflow-hidden border border-slate-200 bg-white shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
                <p className="flex min-w-0 items-center gap-2 text-xs font-medium text-slate-600">
                  <FileText className="h-4 w-4 shrink-0 text-teal-600" />
                  <span className="truncate">
                    {expanded.kind === "file" ? expanded.name : "Artifact preview"}
                  </span>
                </p>
                <div className="flex shrink-0 items-center gap-1">
                  {expanded.kind === "file" && (
                    <a
                      href={expanded.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-600 transition hover:border-teal-500/40 hover:text-teal-700"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Open
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() => setExpanded(null)}
                    className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-900"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {expanded.kind === "html" ? (
                <div className="overflow-auto p-6">
                  <div
                    className="artifact-viewer answer-html mx-auto"
                    dangerouslySetInnerHTML={{ __html: expanded.html }}
                  />
                </div>
              ) : (
                <div className="min-h-0 flex-1 bg-slate-100 p-4">
                  <ArtifactEmbed url={expanded.url} kind={expanded.fileType} full />
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  );
}
