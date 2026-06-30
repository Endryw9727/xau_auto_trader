import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, Loader2, FlaskConical } from "lucide-react";
import api from "@/lib/api";
import { Chip, Panel, Verdict, TStat, PValue, RobustCell, BoolCell, Num } from "@/components/widgets";

const TABS = [
  { id: "session-scan", label: "Session Scan", endpoint: "/edge/session-scan" },
  { id: "ny-conditional", label: "NY Conditional", endpoint: "/edge/ny-conditional" },
  { id: "overnight", label: "Overnight", endpoint: "/edge/overnight" },
];
const DEFAULTS = ["XAUUSD", "EURUSD"];

const RIGHT_COLS = ["oos_t_stat", "is_t_stat", "p_value", "sharpe", "win_rate", "expectancy", "n_trades", "mean_net_pct", "trades"];
const PCT_COLS = ["expectancy", "win_rate", "mean_net_pct"];

function headerClass(c) {
  if (c === "mtc_robust") return "text-center col-robust";
  if (RIGHT_COLS.includes(c)) return "text-right";
  return "";
}

function renderDetailCell(c, row) {
  const v = row[c];
  if (c === "mtc_robust") return <RobustCell value={v} />;
  if (c === "oos_t_stat" || c === "is_t_stat") return <TStat value={v} />;
  if (c === "p_value") return <PValue value={v} />;
  if (typeof v === "boolean") return <BoolCell value={v} />;
  if (typeof v === "number") return <Num value={v} digits={PCT_COLS.includes(c) ? 4 : 2} />;
  return <span className="text-term-muted">{v}</span>;
}

function detailRowKey(row, idx) {
  return [row.symbol, row.session || row.condition || row.leg || "", row.hypothesis || "", row.direction || "", idx].join("-");
}

export default function EdgeLab() {
  const [tab, setTab] = useState(TABS[0]);
  const [selected, setSelected] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const { data: instData } = useQuery({
    queryKey: ["instruments"],
    queryFn: async () => (await api.get("/instruments")).data,
  });

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post(tab.endpoint, { symbols: selected });
      setResult(data);
    } finally {
      setLoading(false);
    }
  };

  const toggle = (sym) =>
    setSelected((s) => (s.includes(sym) ? s.filter((x) => x !== sym) : [...s, sym]));

  const instruments = instData?.instruments || [];
  const detail = result?.detail || [];
  const detailCols = detail.length ? Object.keys(detail[0]) : [];

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <FlaskConical size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">EDGE LAB</h1>
      </div>

      <div className="flex border border-term-border bg-term-surface w-fit">
        {TABS.map((t) => (
          <button
            key={t.id}
            data-testid={`edge-tab-${t.id}`}
            onClick={() => { setTab(t); setResult(null); }}
            className={`font-mono text-xs px-4 py-2 border-r border-term-border last:border-r-0 transition-colors ${
              tab.id === t.id ? "bg-keep/10 text-keep" : "text-term-muted hover:text-term-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Panel title="Universe" testId="edge-controls"
        right={
          <button
            data-testid="run-edge-button"
            onClick={run}
            disabled={loading || selected.length === 0}
            className="flex items-center gap-1.5 font-mono text-[12px] font-semibold px-3 py-1 bg-keep text-black hover:bg-keep/90 disabled:opacity-50"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} RUN {tab.label.toUpperCase()}
          </button>
        }
      >
        <div className="flex flex-wrap gap-2 p-3">
          {instruments.map((i) => (
            <Chip key={i.symbol} testId={`edge-symbol-${i.symbol}`} active={selected.includes(i.symbol)} onClick={() => toggle(i.symbol)}>
              {i.symbol}
            </Chip>
          ))}
        </div>
      </Panel>

      {/* verdicts */}
      <Panel title="Verdicts" testId="edge-verdicts-panel">
        <div className="overflow-auto">
          <table className="term-table" data-testid="edge-verdicts-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Verdict</th><th>Best Session</th>
                {tab.id === "ny-conditional" && <><th>Condition</th><th>Hypothesis</th></>}
                <th>Direction</th><th className="text-right">Best OOS t-stat</th>
                {tab.id === "overnight" && <><th className="text-right">p-value</th><th className="text-center">BH</th><th className="text-center col-robust">mtc_robust</th></>}
              </tr>
            </thead>
            <tbody>
              {(result?.verdicts || []).map((v) => (
                <tr key={v.symbol} data-testid={`edge-verdict-${v.symbol}`}>
                  <td className="text-term-text">{v.symbol}</td>
                  <td><Verdict value={v.verdict} /></td>
                  <td className="text-term-muted">{v.best_session}</td>
                  {tab.id === "ny-conditional" && <><td className="text-term-muted">{v.best_condition}</td><td className="text-term-muted">{v.best_hypothesis}</td></>}
                  <td className="text-term-muted">{v.best_direction}</td>
                  <td className="text-right"><TStat value={v.best_oos_t_stat} /></td>
                  {tab.id === "overnight" && <><td className="text-right"><PValue value={v.p_value} /></td><td className="text-center"><BoolCell value={v.bh_significant} /></td><td className="text-center col-robust"><RobustCell value={v.mtc_robust} /></td></>}
                </tr>
              ))}
              {!result && !loading && <tr><td colSpan={9} className="text-center text-term-dim py-6">Run a scan to see verdicts.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* detail */}
      {detail.length > 0 && (
        <Panel title={`Detail · ${detail.length} legs`} testId="edge-detail-panel">
          <div className="overflow-auto max-h-[420px]">
            <table className="term-table" data-testid="edge-detail-table">
              <thead>
                <tr>
                  {detailCols.map((c) => (
                    <th key={c} className={headerClass(c)}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.map((row, idx) => (
                  <tr key={detailRowKey(row, idx)}>
                    {detailCols.map((c) => (
                      <td key={c} className={c === "mtc_robust" ? "text-center col-robust" : ""}>
                        {renderDetailCell(c, row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
