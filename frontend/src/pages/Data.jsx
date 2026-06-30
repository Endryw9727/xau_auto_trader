import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import api from "@/lib/api";
import { Panel, Num, OfflineState } from "@/components/widgets";

export default function Data() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["instruments"],
    queryFn: async () => (await api.get("/instruments")).data,
    retry: false,
  });

  const instruments = data?.instruments || [];
  const cols = instruments.length ? Object.keys(instruments[0]) : [];

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Database size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">DATA</h1>
        <span className="font-mono text-[10px] px-1.5 py-0.5 bg-term-surface2 text-term-muted tracking-wider">EXTERNAL API · READ-ONLY</span>
      </div>
      <p className="font-mono text-[12px] text-term-muted -mt-1">
        Strumenti serviti esclusivamente dall'API esterna. Nessun upload, generatore o dato sintetico.
      </p>

      <Panel title={`Instruments · ${instruments.length}`} testId="instruments-panel">
        {isLoading ? (
          <div className="p-4 text-term-dim font-mono text-[12px]">Loading…</div>
        ) : isError ? (
          <OfflineState />
        ) : (
          <div className="overflow-auto">
            <table className="term-table" data-testid="instruments-table">
              <thead>
                <tr>{cols.map((c) => (<th key={c} className={["rows", "cost_per_trade"].includes(c) ? "text-right" : ""}>{c}</th>))}</tr>
              </thead>
              <tbody>
                {instruments.map((inst) => (
                  <tr key={inst.symbol} data-testid={`instrument-row-${inst.symbol}`}>
                    {cols.map((c) => (
                      <td key={c} className={["rows", "cost_per_trade"].includes(c) ? "text-right" : ""}>
                        {c === "symbol" ? <span className="text-term-text font-semibold">{inst[c]}</span> :
                         typeof inst[c] === "boolean" ? <span className={inst[c] ? "text-keep" : "text-term-dim"}>{inst[c] ? "✓" : "—"}</span> :
                         typeof inst[c] === "number" ? <Num value={inst[c]} digits={Number.isInteger(inst[c]) ? 0 : 4} /> :
                         c === "first" || c === "last" ? <span className="text-term-dim text-[11px]">{String(inst[c]).slice(0, 16).replace("T", " ")}</span> :
                         <span className="text-term-muted">{String(inst[c])}</span>}
                      </td>
                    ))}
                  </tr>
                ))}
                {instruments.length === 0 && <tr><td colSpan={Math.max(cols.length, 1)} className="text-center text-term-dim py-6">No instruments.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
