import { useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import api from "@/lib/api";
import { Panel, ApiTable, OfflineState } from "@/components/widgets";

function useReport(name) {
  return useQuery({
    queryKey: ["bot", name],
    queryFn: async () => (await api.get(`/bot/${name}`)).data,
    retry: false,
  });
}

// Renders EXACTLY the arrays/scalars returned by the external API — no app-side shaping.
function ReportBody({ data }) {
  if (!data) return null;
  const arrays = Object.entries(data).filter(([, v]) => Array.isArray(v) && v.length && typeof v[0] === "object");
  const scalars = Object.entries(data).filter(([, v]) => v !== null && typeof v !== "object" && !Array.isArray(v));
  return (
    <div>
      {scalars.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-2 border-b border-term-border bg-term-bg">
          {scalars.map(([k, v]) => (
            <span key={k} className="font-mono text-[10px] text-term-muted">
              {k}=<span className={String(v) === "False" || v === false ? "text-keep" : "text-term-text"}>{String(v)}</span>
            </span>
          ))}
        </div>
      )}
      {arrays.map(([k, v]) => (
        <div key={k}>
          <div className="px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-keep border-b border-term-border">{k}</div>
          <ApiTable rows={v} maxHeight="320px" />
        </div>
      ))}
      {arrays.length === 0 && <div className="p-4 text-term-dim font-mono text-[12px]">No tabular data.</div>}
    </div>
  );
}

function ReportCard({ title, query, testId }) {
  return (
    <Panel title={title} testId={testId}>
      {query.isLoading ? (
        <div className="p-4 text-term-dim font-mono text-[12px]">Loading…</div>
      ) : query.isError ? (
        <OfflineState />
      ) : (
        <ReportBody data={query.data} />
      )}
    </Panel>
  );
}

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
        <span className="font-mono text-[10px] px-1.5 py-0.5 bg-term-surface2 text-term-muted tracking-wider">EXTERNAL API</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <ReportCard title="Rejection Taxonomy" query={rejection} testId="rejection-panel" />
        <ReportCard title="Market Structure" query={structure} testId="structure-panel" />
        <ReportCard title="Quality Review" query={quality} testId="quality-panel" />
        <ReportCard title="Demo Readiness" query={demo} testId="demo-panel" />
      </div>
    </div>
  );
}
