import { ShieldCheck } from "lucide-react";

export function Header() {
  return (
    <header className="glass flex h-14 shrink-0 items-center justify-between border-b border-slate-200/70 bg-white/40 px-5">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-teal-400/40 to-emerald-500/30 ring-1 ring-teal-500/40 shadow-[0_0_18px_rgba(45,212,191,0.25)]">
          <span className="text-lg font-bold text-teal-700">A</span>
        </div>
        <div>
          <h1 className="text-sm font-semibold tracking-wide text-slate-900">
            Al Dente Brain
          </h1>
          <p className="text-[11px] text-slate-500">
            Ask the company. Watch the evidence connect.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-medium text-emerald-700 sm:flex">
          <ShieldCheck className="h-3.5 w-3.5" />
          Source-Locked Mode
        </span>
      </div>
    </header>
  );
}
