import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, Loader2, FlaskConical } from "lucide-react";
import api from "@/lib/api";
import { Chip, Panel, ApiTable, OfflineState } from "@/components/widgets";

const TABS = [
  { id: "session-scan", label: "Session Scan", endpoint: "/edge/session-scan" },
  { id: "ny-conditional", label: "NY Conditional", endpoint: "/edge/ny-conditional" },
  { id: "overnight", label: "Overnight", endpoint: "/edge/overnight" },
];
const DEFAULTS = ["XAUUSD", "EURUSD"];

export default function EdgeLab() {
  const [tab, setTab] = useState(TABS[0]);
  const [selected, setSelected] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);

  const { data: instData } = useQuery({
    queryKey: ["instruments"],
    queryFn: async () => (await api.get("/instruments")).data,
    retry: false,
  });

  const run = async () => {
    setLoading(true);
    setResult(null);
    setOffline(false);
    try {
      const { data } = await api.post(tab.endpoint, { symbols: selected });
      setResult(data);
    } catch (e) {
      setOffline(true);
    } finally {
      setLoading(false);
    }
  };

  const toggle = (sym) =>
    setSelected((s) => (s.includes(sym) ? s.filter((x) => x !== sym) : [...s, sym]));

  const instruments = instData?.instruments || [];
  const verdicts = result?.verdicts || [];
  const rows = result?.detail || result?.rows || [];

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
            onClick={() => { setTab(t); setResult(null); setOffline(false); }}
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
          {instruments.length === 0 && <span className="font-mono text-[11px] text-term-dim">Nessuno strumento (API offline).</span>}
        </div>
      </Panel>

      {offline ? (
        <Panel title="Result" testId="edge-result-panel"><OfflineState /></Panel>
      ) : (
        <>
          {verdicts.length > 0 && (
            <Panel title={`Verdicts · ${verdicts.length}`} testId="edge-verdicts-panel">
              <ApiTable rows={verdicts} testId="edge-verdicts-table" maxHeight="40vh" />
            </Panel>
          )}
          {rows.length > 0 && (
            <Panel title={`${result?.detail ? "Detail" : "Rows"} · ${rows.length}`} testId="edge-detail-panel">
              <ApiTable rows={rows} highlightCol="mtc_robust" testId="edge-detail-table" maxHeight="48vh" />
            </Panel>
          )}
          {!result && !loading && (
            <Panel title="Result" testId="edge-result-panel">
              <div className="p-6 text-center text-term-dim font-mono text-[12px]">Run a scan to see results from the external API.</div>
            </Panel>
          )}
          {result && verdicts.length === 0 && rows.length === 0 && (
            <Panel title="Result" testId="edge-result-panel">
              <div className="p-6 text-center text-term-dim font-mono text-[12px]">The API returned no rows for this selection.</div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
