import { useQuery } from "@tanstack/react-query";
import { Bot, ShieldCheck, ShieldAlert, Activity, ClipboardCheck } from "lucide-react";
import api from "@/lib/api";
import { Panel, Num, BoolCell } from "@/components/widgets";

function useReport(name) {
  return useQuery({ queryKey: ["bot", name], queryFn: async () => (await api.get(`/bot/${name}`)).data });
}

const statusColor = (s) => (s === "PASS" ? "text-keep" : s === "WARN" ? "text-warn" : "text-exclude");

export default function BotDiagnostics() {
  const rejection = useReport("rejection-taxonomy");
  const structure = useReport("market-structure");
  const quality = useReport("quality-review");
  const demo = useReport("demo-readiness");

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Bot size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">BOT DIAGNOSTICS</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Rejection taxonomy */}
        <Panel title={`Rejection Taxonomy · ${rejection.data?.total_rejections?.toLocaleString() ?? "…"} total`} testId="rejection-panel">
          <div className="p-2">
            {(rejection.data?.buckets || []).map((b) => (
              <div key={b.reason} className="flex items-center gap-2 py-1" data-testid={`rejection-${b.reason}`}>
                <span className="font-mono text-[11px] text-term-muted w-40 shrink-0">{b.reason}</span>
                <div className="flex-1 h-3 bg-term-bg border border-term-border">
                  <div className="h-full bg-exclude/50" style={{ width: `${b.pct}%` }} />
                </div>
                <span className="num text-[11px] text-term-text w-16">{b.pct}%</span>
                <span className="num text-[11px] text-term-dim w-14"><Num value={b.count} digits={0} /></span>
              </div>
            ))}
          </div>
        </Panel>

        {/* Market structure */}
        <Panel title="Market Structure" testId="structure-panel"
          right={<span className="font-mono text-[10px] text-term-muted">ADX {structure.data?.trend_strength_adx ?? "—"}</span>}>
          <div className="overflow-auto">
            <table className="term-table" data-testid="structure-table">
              <thead><tr><th>Regime</th><th className="text-right">% Time</th><th className="text-right">Avg ATR</th><th className="text-right">Trades</th></tr></thead>
              <tbody>
                {(structure.data?.regimes || []).map((r) => (
                  <tr key={r.regime}>
                    <td className="text-term-text flex items-center gap-1"><Activity size={11} className="text-keep" />{r.regime}</td>
                    <td className="text-right"><Num value={r.pct_time} digits={1} /></td>
                    <td className="text-right"><Num value={r.avg_atr} digits={2} /></td>
                    <td className="text-right"><Num value={r.trades} digits={0} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Quality review */}
        <Panel title="Quality Review" testId="quality-panel"
          right={<span className={`font-mono text-sm font-bold ${quality.data?.score >= 80 ? "text-keep" : quality.data?.score >= 60 ? "text-warn" : "text-exclude"}`}>{quality.data?.score ?? "—"}/100</span>}>
          <div className="p-2">
            {(quality.data?.checks || []).map((c) => (
              <div key={c.name} className="flex items-center justify-between py-1.5 border-b border-term-surface2 last:border-0" data-testid={`quality-${c.name}`}>
                <span className="flex items-center gap-2 font-mono text-[12px] text-term-text"><ClipboardCheck size={12} className="text-term-muted" />{c.name}</span>
                <span className={`font-mono text-[11px] font-semibold ${statusColor(c.status)}`}>{c.status}</span>
              </div>
            ))}
          </div>
        </Panel>

        {/* Demo readiness */}
        <Panel title="Demo Readiness" testId="demo-panel"
          right={
            demo.data ? (
              <span className={`flex items-center gap-1 font-mono text-[11px] font-semibold ${demo.data.ready_for_demo ? "text-keep" : "text-warn"}`}>
                {demo.data.ready_for_demo ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />}
                {demo.data.ready_for_demo ? "READY" : "BLOCKED"}
              </span>
            ) : null
          }>
          <div className="p-2">
            <div className="mb-2 px-2 py-1.5 bg-warn/10 border border-warn/40 font-mono text-[11px] text-warn">
              live_armed = false · allow_real_live = false
            </div>
            {(demo.data?.gates || []).map((g) => (
              <div key={g.gate} className="flex items-center justify-between py-1.5 border-b border-term-surface2 last:border-0" data-testid={`gate-${g.gate}`}>
                <span className="font-mono text-[12px] text-term-text">{g.gate}</span>
                <BoolCell value={g.passed} />
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
