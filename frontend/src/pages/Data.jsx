import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Database, Upload, Sparkles, Download, Loader2 } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, YAxis, Tooltip } from "recharts";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { Panel, Num } from "@/components/widgets";

export default function Data() {
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [synthSymbol, setSynthSymbol] = useState("SYNTH1");
  const [synthRows, setSynthRows] = useState(500);
  const [yahooSymbol, setYahooSymbol] = useState("AAPL");
  const [preview, setPreview] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["instruments"],
    queryFn: async () => (await api.get("/instruments")).data,
  });

  const uploadMut = useMutation({
    mutationFn: async (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return (await api.post("/data/upload-csv", fd, { headers: { "Content-Type": "multipart/form-data" } })).data;
    },
    onSuccess: (d) => { toast.success(`Uploaded ${d.symbol} (${d.rows} rows)`); qc.invalidateQueries({ queryKey: ["instruments"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  const synthMut = useMutation({
    mutationFn: async () => (await api.post("/data/synthetic", { symbol: synthSymbol, rows: Number(synthRows) })).data,
    onSuccess: (d) => { toast.success(`Generated ${d.instrument.symbol}`); setPreview({ symbol: d.instrument.symbol, series: d.preview }); qc.invalidateQueries({ queryKey: ["instruments"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  const yahooMut = useMutation({
    mutationFn: async () => (await api.post("/data/fetch-yahoo", { symbol: yahooSymbol })).data,
    onSuccess: (d) => { toast.success(`Fetched ${d.instrument.symbol}${d.note ? " · " + d.note : ""}`); setPreview({ symbol: d.instrument.symbol, series: d.preview }); qc.invalidateQueries({ queryKey: ["instruments"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  const instruments = data?.instruments || [];

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Database size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">DATA</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Panel title="Upload CSV" testId="upload-panel">
          <div className="p-3 space-y-2">
            <p className="font-mono text-[11px] text-term-muted">Format: Date,Open,High,Low,Close,Volume</p>
            <input ref={fileRef} type="file" accept=".csv" className="hidden" data-testid="csv-file-input"
              onChange={(e) => e.target.files?.[0] && uploadMut.mutate(e.target.files[0])} />
            <button data-testid="upload-csv-button" onClick={() => fileRef.current?.click()} disabled={uploadMut.isPending}
              className="w-full flex items-center justify-center gap-2 font-mono text-xs py-2 border border-term-border text-term-text hover:bg-term-surface2 disabled:opacity-50">
              {uploadMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} SELECT CSV
            </button>
          </div>
        </Panel>

        <Panel title="Synthetic Generator" testId="synthetic-panel">
          <div className="p-3 space-y-2">
            <div className="flex gap-2">
              <input data-testid="synth-symbol-input" value={synthSymbol} onChange={(e) => setSynthSymbol(e.target.value.toUpperCase())}
                className="flex-1 bg-term-bg border border-term-border px-2 py-1.5 font-mono text-xs outline-none focus:border-keep" placeholder="SYMBOL" />
              <input data-testid="synth-rows-input" type="number" value={synthRows} onChange={(e) => setSynthRows(e.target.value)}
                className="w-24 bg-term-bg border border-term-border px-2 py-1.5 font-mono text-xs outline-none focus:border-keep" placeholder="rows" />
            </div>
            <button data-testid="generate-synthetic-button" onClick={() => synthMut.mutate()} disabled={synthMut.isPending}
              className="w-full flex items-center justify-center gap-2 font-mono text-xs py-2 bg-keep text-black font-semibold hover:bg-keep/90 disabled:opacity-50">
              {synthMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} GENERATE
            </button>
          </div>
        </Panel>

        <Panel title="Fetch (Yahoo)" testId="yahoo-panel">
          <div className="p-3 space-y-2">
            <input data-testid="yahoo-symbol-input" value={yahooSymbol} onChange={(e) => setYahooSymbol(e.target.value.toUpperCase())}
              className="w-full bg-term-bg border border-term-border px-2 py-1.5 font-mono text-xs outline-none focus:border-keep" placeholder="AAPL" />
            <button data-testid="fetch-yahoo-button" onClick={() => yahooMut.mutate()} disabled={yahooMut.isPending}
              className="w-full flex items-center justify-center gap-2 font-mono text-xs py-2 border border-term-border text-term-text hover:bg-term-surface2 disabled:opacity-50">
              {yahooMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} FETCH
            </button>
            <p className="font-mono text-[10px] text-term-dim">Routes to external API when connected; synthetic fallback otherwise.</p>
          </div>
        </Panel>
      </div>

      {preview && (
        <Panel title={`Preview · ${preview.symbol} (last ${preview.series.length})`} testId="data-preview-panel">
          <div className="h-40 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={preview.series}>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363D", fontFamily: "IBM Plex Mono", fontSize: 11 }} labelStyle={{ display: "none" }} />
                <Line type="monotone" dataKey="close" stroke="#00FF9D" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      <Panel title={`Instruments · ${instruments.length}`} testId="instruments-panel">
        <div className="overflow-auto">
          <table className="term-table" data-testid="instruments-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Source</th><th className="text-center">Has Data</th>
                <th className="text-right">Rows</th><th>First</th><th>Last</th><th className="text-right">Cost/Trade</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map((i) => (
                <tr key={i.symbol} data-testid={`instrument-row-${i.symbol}`}>
                  <td className="text-term-text font-semibold">{i.symbol}</td>
                  <td className="text-term-muted">{i.source}</td>
                  <td className="text-center text-keep">{i.has_data ? "✓" : "—"}</td>
                  <td className="text-right"><Num value={i.rows} digits={0} /></td>
                  <td className="text-term-dim text-[11px]">{String(i.first).slice(0, 10)}</td>
                  <td className="text-term-dim text-[11px]">{String(i.last).slice(0, 10)}</td>
                  <td className="text-right"><Num value={i.cost_per_trade} digits={2} /></td>
                </tr>
              ))}
              {isLoading && <tr><td colSpan={7} className="text-center text-term-dim py-6">Loading…</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
