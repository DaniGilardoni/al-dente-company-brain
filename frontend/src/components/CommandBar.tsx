import { ArrowUp, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface CommandBarProps {
  onSubmit: (question: string) => void;
  loading: boolean;
  /** Text pushed into the input on entity selection; nonce re-triggers it. */
  prefill?: { text: string; nonce: number } | null;
  /** True once a memo/thread is open, to switch the prompt copy. */
  conversing?: boolean;
}

export function CommandBar({ onSubmit, loading, prefill, conversing }: CommandBarProps) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  // When a node is selected, drop its reference into the input and focus it.
  useEffect(() => {
    if (!prefill?.text) return;
    setValue(prefill.text);
    const el = taRef.current;
    if (el) {
      el.focus();
      requestAnimationFrame(() => {
        const len = el.value.length;
        el.setSelectionRange(len, len);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.nonce]);

  const submit = useCallback(() => {
    const q = value.trim();
    if (!q || loading) return;
    onSubmit(q);
    setValue("");
  }, [value, loading, onSubmit]);

  return (
    <footer className="glass shrink-0 border-t border-slate-200/70 bg-white/50 px-4 pb-3 pt-3">
      <div className="mx-auto w-full max-w-4xl">
        <div className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={taRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder={conversing ? "Continue to query…" : "Ask the company brain…"}
              disabled={loading}
              className="w-full resize-none rounded-xl border border-slate-200 bg-white/70 px-4 py-3 pr-14 text-sm text-slate-800 shadow-inner shadow-slate-900/5 transition placeholder:text-slate-400 focus:border-teal-500/50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-500/30 disabled:opacity-50"
            />
            <span className="pointer-events-none absolute bottom-3 right-3 hidden text-[10px] text-slate-400 sm:inline">
              ↵ send
            </span>
          </div>
          <button
            type="button"
            onClick={submit}
            disabled={loading || !value.trim()}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-emerald-600 text-white shadow-lg shadow-teal-500/30 transition hover:from-teal-400 hover:to-emerald-500 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <ArrowUp className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>
    </footer>
  );
}
