import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BrainCircuit, Send, Loader2, Lock, Paperclip, Bot, User } from "lucide-react";
import api from "@/lib/api";
import { Panel } from "@/components/widgets";

let _msgSeq = 0;
const newMsg = (msg) => ({ id: ++_msgSeq, ...msg });

function bubbleClass(m) {
  const base = "max-w-[85%] px-3 py-2 border font-mono text-[12.5px] whitespace-pre-wrap leading-relaxed ";
  if (m.role === "user") return base + "border-term-border bg-term-surface2 text-term-text";
  if (m.error) return base + "border-exclude/40 bg-exclude/10 text-exclude";
  return base + "border-keep/30 bg-keep/[0.04] text-term-text";
}

export default function AIResearch() {
  const [task, setTask] = useState("explain_significance");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [contextRunId, setContextRunId] = useState("");
  const [contextData, setContextData] = useState(null);
  const endRef = useRef(null);

  const { data: config } = useQuery({ queryKey: ["ai-config"], queryFn: async () => (await api.get("/ai/config")).data });
  const { data: runsData } = useQuery({ queryKey: ["runs"], queryFn: async () => (await api.get("/runs")).data });

  const tasks = config?.tasks || {};
  const providers = config?.providers || [];

  useEffect(() => {
    if (config && tasks[task]) { setProvider(tasks[task].provider); setModel(tasks[task].model); }
    // re-sync the model override whenever the selected task or config changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, config]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const attachRun = async (runId) => {
    setContextRunId(runId);
    if (!runId) { setContextData(null); return; }
    const { data } = await api.get(`/runs/${runId}`);
    setContextData({ run_type: data.run_type, params: data.params, result: data.result });
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = newMsg({ role: "user", content: input });
    setMessages((m) => [...m, userMsg]);
    const question = input;
    setInput("");
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", {
        task, provider, model, message: question, context: contextData, conversation_id: conversationId,
      });
      setConversationId(data.conversation_id);
      setMessages((m) => [...m, newMsg({ role: "assistant", content: data.reply, provider: data.provider, model: data.model })]);
    } catch (e) {
      setMessages((m) => [...m, newMsg({ role: "assistant", content: `⚠ ${e.response?.data?.detail || e.message}`, error: true })]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <BrainCircuit size={18} className="text-keep" />
        <h1 className="font-mono font-semibold tracking-tight text-base text-term-text">AI RESEARCH</h1>
        <span className="flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 bg-warn/15 text-warn tracking-wider">
          <Lock size={10} /> REPORT-ONLY
        </span>
      </div>

      <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        {/* LEFT: routing */}
        <div className="col-span-12 lg:col-span-3 space-y-3 overflow-auto">
          <Panel title="Task Routing" testId="task-routing-panel">
            <div className="p-2 space-y-1">
              {Object.entries(tasks).map(([key, t]) => (
                <button key={key} data-testid={`task-${key}`} onClick={() => setTask(key)}
                  className={`w-full text-left px-2 py-2 border transition-colors ${task === key ? "border-keep/70 bg-keep/10" : "border-term-border hover:bg-term-surface2"}`}>
                  <div className={`font-mono text-[12px] ${task === key ? "text-keep" : "text-term-text"}`}>{t.label}</div>
                  <div className="font-mono text-[10px] text-term-dim mt-0.5">{t.desc}</div>
                  <div className="font-mono text-[10px] text-term-muted mt-1">→ {t.provider}/{t.model}</div>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Model Override" testId="model-panel">
            <div className="p-2">
              <select data-testid="provider-select" value={`${provider}|${model}`}
                onChange={(e) => { const [p, m] = e.target.value.split("|"); setProvider(p); setModel(m); }}
                className="w-full bg-term-bg border border-term-border px-2 py-1.5 font-mono text-xs text-term-text outline-none focus:border-keep">
                {providers.map((p) => (
                  <option key={`${p.id}|${p.model}`} value={`${p.id}|${p.model}`} disabled={!p.enabled}>
                    {p.label}{!p.enabled ? " (disabled)" : ""}
                  </option>
                ))}
              </select>
              <p className="font-mono text-[10px] text-term-dim mt-2">Active: {provider}/{model}</p>
            </div>
          </Panel>
        </div>

        {/* MIDDLE: chat */}
        <div className="col-span-12 lg:col-span-6 flex flex-col min-h-0">
          <Panel title="Research Stream" testId="chat-panel" className="flex-1 flex flex-col min-h-0">
            <div className="flex-1 overflow-auto p-3 space-y-3" data-testid="chat-messages">
              {messages.length === 0 && (
                <div className="text-center text-term-dim font-mono text-[12px] py-10">
                  Attach a run for context, pick a task, and ask the model to interpret the metrics.
                  <br /><span className="text-warn">Models never compute statistics or place orders.</span>
                </div>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`flex gap-2 ${m.role === "user" ? "justify-end" : ""}`}>
                  {m.role === "assistant" && <Bot size={16} className={`shrink-0 mt-1 ${m.error ? "text-exclude" : "text-keep"}`} />}
                  <div className={bubbleClass(m)}>
                    {m.role === "assistant" && !m.error && (
                      <div className="font-mono text-[9px] text-term-muted mb-1 uppercase">{m.provider}/{m.model}</div>
                    )}
                    {m.content}
                  </div>
                  {m.role === "user" && <User size={16} className="shrink-0 mt-1 text-term-muted" />}
                </div>
              ))}
              {loading && (
                <div className="flex gap-2"><Bot size={16} className="text-keep mt-1" />
                  <div className="px-3 py-2 border border-keep/30 bg-keep/[0.04] font-mono text-[12px] text-term-muted animate-blink">analyzing metrics…</div>
                </div>
              )}
              <div ref={endRef} />
            </div>
            <div className="border-t border-term-border p-2 flex gap-2">
              <input data-testid="chat-input" value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Ask about the attached metrics…"
                className="flex-1 bg-term-bg border border-term-border px-3 py-2 font-mono text-[13px] text-term-text outline-none focus:border-keep" />
              <button data-testid="chat-send-button" onClick={send} disabled={loading || !input.trim()}
                className="px-4 bg-keep text-black font-semibold hover:bg-keep/90 disabled:opacity-50 flex items-center gap-1">
                {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              </button>
            </div>
          </Panel>
        </div>

        {/* RIGHT: context */}
        <div className="col-span-12 lg:col-span-3 space-y-3 overflow-auto">
          <Panel title="Metrics Context" testId="context-panel">
            <div className="p-2 space-y-2">
              <label className="font-mono text-[10px] text-term-muted flex items-center gap-1"><Paperclip size={10} /> ATTACH RUN</label>
              <select data-testid="context-run-select" value={contextRunId} onChange={(e) => attachRun(e.target.value)}
                className="w-full bg-term-bg border border-term-border px-2 py-1.5 font-mono text-[11px] text-term-text outline-none focus:border-keep">
                <option value="">— none —</option>
                {(runsData?.runs || []).map((r) => (
                  <option key={r.id} value={r.id}>{`${r.run_type} · ${r.created_at.slice(5, 16).replace("T", " ")}`}</option>
                ))}
              </select>
              {contextData ? (
                <pre data-testid="context-preview" className="bg-term-bg border border-term-border p-2 font-mono text-[10px] text-term-muted max-h-64 overflow-auto">
                  {JSON.stringify(contextData, null, 1).slice(0, 1500)}
                </pre>
              ) : (
                <p className="font-mono text-[10px] text-term-dim">No context attached. The model will answer generally.</p>
              )}
            </div>
          </Panel>
          <Panel title="Guardrails" testId="guardrails-panel">
            <ul className="p-3 space-y-1.5 font-mono text-[10.5px] text-term-muted list-none">
              <li className="text-keep">✓ Receives only pre-computed metrics</li>
              <li className="text-keep">✓ Explains & proposes hypotheses</li>
              <li className="text-exclude">✗ Cannot compute statistics</li>
              <li className="text-exclude">✗ Cannot place / arm orders</li>
              <li className="text-warn">allow_real_live = false (locked)</li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
