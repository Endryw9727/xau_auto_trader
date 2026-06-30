import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, Loader2, Filter, Gavel } from "lucide-react";
import api from "@/lib/api";
import { StatTile, RobustCell, BoolCell, PValue, TStat, Chip, Panel, OfflineState } from "@/components/widgets";

const DEFAULTS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"];

export default function SignificanceAudit() {
  const [selected, setSelected] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [onlyRobust, setOnlyRobust] = useState(false);
  const [offline, setOffline] = useState(false);

  const { data: instData } = useQuery({
    queryKey: ["instruments"],
    queryFn: async () => (await api.get("/instruments")).data,
    retry: false,
  });

  const run = async (symbols) => {
    setLoading(true);
    setOffline(false);
    try {
      const { data } = await api.post("/edge/significance-audit", { symbols });
      setResult(data);
    } catch (e) {
      setResult(null);
      setOffline(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    run(DEFAULTS);
    // auto-run once on mount with the default universe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (sym) =>
    setSelected((s) => (s.includes(sym) ? s.filter((x) => x !== sym) : [...s, sym]));

  const rows = useMemo(() => {
    if (!result) return [];
    return onlyRobust ? result.rows.filter((r) => r.mtc_robust) : result.rows;
  }, [result, onlyRobust]);

  const instruments = instData?.instruments || [];

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Gavel size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">SIGNIFICANCE AUDIT</h1>
        <span className="font-mono text-[10px] px-1.5 py-0.5 bg-keep/15 text-keep tracking-wider">PRIMARY VERDICT</span>
      </div>
      <p className="font-mono text-[12px] text-term-muted -mt-1 max-w-3xl">
        Multiple-testing-correction verdict across the hypothesis family. A combo is trustworthy
        only if <span className="text-robust">mtc_robust = true</span> (survives Bonferroni + Benjamini-Hochberg).
      </p>

      {/* counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile testId="stat-family-size" label="Family Size" value={result?.family_size ?? "—"} />
        <StatTile
          testId="stat-mtc-survivors"
          label="MTC Survivors"
          value={result?.mtc_survivors ?? "—"}
          accent={result?.mtc_survivors > 0 ? "text-robust" : "text-term-dim"}
          style={result?.mtc_survivors > 0 ? { textShadow: "0 0 10px rgba(0,255,157,0.6)" } : undefined}
        />
        <StatTile testId="stat-symbols" label="Symbols" value={selected.length} />
        <StatTile
          testId="stat-survival-rate"
          label="Survival Rate"
          value={result ? `${((100 * result.mtc_survivors) / Math.max(result.family_size, 1)).toFixed(1)}%` : "—"}
          accent="text-warn"
        />
      </div>

      {/* controls */}
      <Panel title="Run Audit" testId="audit-controls"
        right={
          <div className="flex items-center gap-2">
            <button
              data-testid="toggle-only-robust"
              onClick={() => setOnlyRobust((v) => !v)}
              className={`flex items-center gap-1 font-mono text-[11px] px-2 py-1 border ${
                onlyRobust ? "border-keep/70 text-keep bg-keep/10" : "border-term-border text-term-muted"
              }`}
            >
              <Filter size={11} /> ROBUST ONLY
            </button>
            <button
              data-testid="run-audit-button"
              onClick={() => run(selected)}
              disabled={loading || selected.length === 0}
              className="flex items-center gap-1.5 font-mono text-[12px] font-semibold px-3 py-1 bg-keep text-black hover:bg-keep/90 disabled:opacity-50"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} RUN
            </button>
          </div>
        }
      >
        <div className="flex flex-wrap gap-2 p-3">
          {instruments.map((i) => (
            <Chip key={i.symbol} testId={`symbol-chip-${i.symbol}`} active={selected.includes(i.symbol)} onClick={() => toggle(i.symbol)}>
              {i.symbol}
            </Chip>
          ))}
        </div>
      </Panel>

      {/* hero table */}
      <Panel title={`Hypothesis Family · ${rows.length} combos`} testId="audit-table-panel">
        {offline ? (
          <OfflineState />
        ) : (
        <div className="overflow-auto max-h-[calc(100vh-440px)]">
          <table className="term-table" data-testid="significance-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Combo</th>
                <th className="text-right">OOS t-stat</th>
                <th className="text-right">p-value</th>
                <th className="text-center">Bonferroni</th>
                <th className="text-center">BH</th>
                <th className="text-center col-robust" style={{ background: "rgba(0,255,157,0.1)", color: "#00FF9D" }}>
                  mtc_robust
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={`${r.symbol}-${r.combo}`} data-testid={`sig-row-${idx}`} className={r.mtc_robust ? "bg-robust/[0.04]" : ""}>
                  <td className="text-term-text">{r.symbol}</td>
                  <td className="text-term-muted">{r.combo}</td>
                  <td className="text-right"><TStat value={r.oos_t_stat} /></td>
                  <td className="text-right"><PValue value={r.p_value} /></td>
                  <td className="text-center"><BoolCell value={r.bonferroni_significant} /></td>
                  <td className="text-center"><BoolCell value={r.bh_significant} /></td>
                  <td className="text-center col-robust"><RobustCell value={r.mtc_robust} testId={`robust-${idx}`} /></td>
                </tr>
              ))}
              {rows.length === 0 && !loading && (
                <tr><td colSpan={7} className="text-center text-term-dim py-6">No combos.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        )}
      </Panel>
    </div>
  );
}
