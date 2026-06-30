import { cn } from "@/lib/utils";
import { Check, X, Zap } from "lucide-react";

export function Panel({ title, right, children, className, testId }) {
  return (
    <section
      data-testid={testId}
      className={cn("bg-term-surface border border-term-border", className)}
    >
      {(title || right) && (
        <header className="flex items-center justify-between px-3 py-2 border-b border-term-border bg-term-bg">
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-term-muted">{title}</h3>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Num({ value, digits = 2, className }) {
  const n = typeof value === "number" ? value.toFixed(digits) : value ?? "—";
  return <span className={cn("num", className)}>{n}</span>;
}

export function Verdict({ value }) {
  const keep = value === "KEEP";
  return (
    <span
      data-testid={`verdict-${value}`}
      className={cn(
        "font-mono text-[11px] font-semibold px-2 py-0.5 border",
        keep
          ? "text-keep border-keep/60 bg-keep/10"
          : "text-term-muted border-term-border bg-exclude/10"
      )}
    >
      {keep ? "KEEP" : "EXCLUDE"}
    </span>
  );
}

export function RobustCell({ value, testId }) {
  if (value) {
    return (
      <span
        data-testid={testId || "mtc-robust-true"}
        className="robust-glow inline-flex items-center gap-1 font-mono text-[11px] font-bold text-robust bg-robust/15 px-2 py-0.5"
      >
        <Zap size={11} strokeWidth={2.5} /> ROBUST
      </span>
    );
  }
  return <span data-testid="mtc-robust-false" className="font-mono text-[12px] text-term-dim">—</span>;
}

export function BoolCell({ value }) {
  return value ? (
    <Check size={14} className="text-keep inline" strokeWidth={2.5} />
  ) : (
    <X size={14} className="text-term-dim inline" strokeWidth={2} />
  );
}

export function PValue({ value }) {
  const sig = typeof value === "number" && value < 0.05;
  return (
    <span className={cn("num", sig ? "text-warn" : "text-term-muted")}>
      {typeof value === "number" ? value.toFixed(4) : "—"}
    </span>
  );
}

export function TStat({ value }) {
  const strong = typeof value === "number" && Math.abs(value) >= 2.0;
  const pos = typeof value === "number" && value > 0;
  return (
    <span className={cn("num", strong ? (pos ? "text-keep" : "text-exclude") : "text-term-text")}>
      {typeof value === "number" ? value.toFixed(2) : "—"}
    </span>
  );
}

export function StatTile({ label, value, accent, testId, style }) {
  return (
    <div data-testid={testId} className="bg-term-surface border border-term-border px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-term-muted">{label}</div>
      <div className={cn("font-mono text-2xl font-semibold mt-1", accent || "text-term-text")} style={style}>{value}</div>
    </div>
  );
}

export function Chip({ active, onClick, children, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      className={cn(
        "font-mono text-[12px] px-2.5 py-1 border transition-colors",
        active
          ? "border-keep/70 text-keep bg-keep/10"
          : "border-term-border text-term-muted hover:bg-term-surface2 hover:text-term-text"
      )}
    >
      {children}
    </button>
  );
}
