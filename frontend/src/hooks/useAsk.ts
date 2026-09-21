import { useCallback, useRef, useState } from "react";
import type { AskResponse, HistoryItem, Turn } from "../types/ask";

function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

/** Fold completed turns into a context preamble for follow-up questions. */
function buildContext(turns: Turn[]): string | undefined {
  const done = turns.filter((t) => t.answer);
  if (done.length === 0) return undefined;
  const parts = done.map(
    (t) => `Q: ${t.question}\nA: ${stripHtml(t.answer!.answer).slice(0, 1200)}`,
  );
  return `Conversation so far:\n${parts.join("\n\n")}`;
}

export function useAsk() {
  const [loading, setLoading] = useState(false);
  const [thread, setThread] = useState<Turn[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  // Mirror thread in a ref so ask() reads the latest turns without re-creating.
  const threadRef = useRef<Turn[]>([]);
  threadRef.current = thread;

  const ask = useCallback(async (question: string) => {
    // Follow-up context is folded into the question string; the /ask contract
    // is unchanged (still `{question}`), and the raw question is what we show.
    const context = buildContext(threadRef.current);
    const payload = context
      ? `${context}\n\n---\nFollow-up question (same conversation): ${question}`
      : question;

    const turnId = Date.now();
    setThread((t) => [...t, { id: turnId, question, answer: null, error: null }]);
    setLoading(true);

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: payload }),
      });
      const data = (await res.json()) as AskResponse;
      setThread((t) =>
        t.map((x) => (x.id === turnId ? { ...x, answer: data } : x)),
      );
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setThread((t) =>
        t.map((x) => (x.id === turnId ? { ...x, error: msg } : x)),
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Archive the current chat and start a fresh thread.
  const newChat = useCallback(() => {
    setThread((t) => {
      if (t.length > 0) {
        const first = t[0];
        setHistory((h) => [
          ...h,
          { id: first.id, question: first.question, turns: t, at: Date.now() },
        ]);
      }
      return [];
    });
  }, []);

  // Load a past chat back into the thread.
  const restore = useCallback((item: HistoryItem) => {
    setThread(item.turns);
  }, []);

  return { ask, newChat, restore, thread, history, loading };
}
