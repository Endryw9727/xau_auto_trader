import { cn } from "@/lib/utils";
import { Check, X, Zap, WifiOff } from "lucide-react";

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

export function OfflineState({ message = "API OFFLINE — nessun dato" }) {
  return (
    <div data-testid="api-offline" className="flex flex-col items-center justify-center gap-2 py-14 px-4 text-center">
      <WifiOff size={28} strokeWidth={1.5} className="text-exclude" />
      <div className="font-mono text-sm text-exclude tracking-wider">{message}</div>
      <div className="font-mono text-[11px] text-term-dim max-w-md">
        L'API esterna non è raggiungibile. Non viene mostrato alcun dato fittizio.
      </div>
    </div>
  );
}

// Generic renderer that displays EXACTLY the rows returned by the external API,
// with no app-side computation. Column set is derived from the data itself.
const HIGH_PREC = ["avg_r", "total_r", "expectancy", "mean_net_pct", "daily_r", "cumulative_r", "drawdown_r", "sharpe"];
const RIGHT_HINTS = ["t_stat", "p_value", "count", "pct", "share", "rows", "trades", "wins", "rate",
  "avg", "total", "expectancy", "candidates", "accepted", "rejected", "buy", "sell", "_r", "cost", "net", "drawdown", "cumulative", "daily"];

function isNumericKey(k) {
  const lk = k.toLowerCase();
  return RIGHT_HINTS.some((h) => lk.includes(h));
}

function renderCell(key, v, highlightCol) {
  const lk = key.toLowerCase();
  if (key === highlightCol || lk === "mtc_robust" || lk === "robust_edge") return <RobustCell value={!!v} />;
  if (lk === "verdict") return <Verdict value={v} />;
  if (lk.includes("t_stat")) return <TStat value={typeof v === "number" ? v : Number(v)} />;
  if (lk === "p_value") return <PValue value={typeof v === "number" ? v : Number(v)} />;
  if (typeof v === "boolean") return <BoolCell value={v} />;
  if (typeof v === "number") {
    const digits = HIGH_PREC.includes(lk) ? 4 : Number.isInteger(v) ? 0 : 2;
    return <Num value={v} digits={digits} />;
  }
  if (v == null) return <span className="text-term-dim">—</span>;
  return <span className="text-term-muted">{String(v)}</span>;
}

export function ApiTable({ rows, columns, highlightCol = "mtc_robust", testId, maxHeight = "60vh" }) {
  if (!rows || rows.length === 0) {
    return <div className="p-4 text-term-dim font-mono text-[12px]">No rows.</div>;
  }
  const cols = columns || Object.keys(rows[0]);
  const headCls = (c) => (c === highlightCol ? "text-center col-robust" : isNumericKey(c) ? "text-right" : "");
  return (
    <div className="overflow-auto" style={{ maxHeight }}>
      <table className="term-table" data-testid={testId}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                className={headCls(c)}
                style={c === highlightCol ? { background: "rgba(0,255,157,0.1)", color: "#00FF9D" } : undefined}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={row[highlightCol] ? "bg-robust/[0.04]" : ""}>
              {cols.map((c) => (
                <td key={c} className={c === highlightCol ? "text-center col-robust" : isNumericKey(c) ? "text-right" : ""}>
                  {renderCell(c, row[c], highlightCol)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
