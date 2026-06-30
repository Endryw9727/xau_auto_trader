import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Terminal, ShieldOff, Loader2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/lib/api";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("admin@research.console");
  const [password, setPassword] = useState("ResearchAdmin2025");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
      navigate("/significance-audit");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-term-bg flex items-center justify-center relative overflow-hidden">
      <img
        src="https://images.pexels.com/photos/7599718/pexels-photo-7599718.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
        alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-[0.07]"
      />
      <div className="absolute inset-0 bg-gradient-to-b from-term-bg/40 to-term-bg" />

      <div className="relative w-full max-w-sm px-6 animate-fade-up">
        <div className="flex items-center gap-2 text-keep mb-1">
          <Terminal size={22} strokeWidth={2} />
          <h1 className="font-mono font-semibold tracking-tight text-lg text-term-text">RESEARCH CONSOLE</h1>
        </div>
        <p className="font-mono text-[11px] text-term-dim tracking-wider mb-6">
          QUANTITATIVE EDGE RESEARCH · READ-ONLY
        </p>

        <div className="bg-term-surface border border-term-border">
          <div className="flex border-b border-term-border">
            {["login", "register"].map((m) => (
              <button
                key={m}
                data-testid={`auth-tab-${m}`}
                onClick={() => { setMode(m); setError(""); }}
                className={`flex-1 font-mono text-xs uppercase tracking-wider py-2.5 transition-colors ${
                  mode === m ? "text-keep border-b-2 border-keep -mb-px bg-keep/5" : "text-term-muted hover:text-term-text"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="p-5 space-y-3">
            {mode === "register" && (
              <Field label="NAME" value={name} onChange={setName} testId="register-name" placeholder="analyst" />
            )}
            <Field label="EMAIL" value={email} onChange={setEmail} testId="login-email" type="email" placeholder="you@desk.io" />
            <Field label="PASSWORD" value={password} onChange={setPassword} testId="login-password" type="password" placeholder="••••••••" />

            {error && (
              <div data-testid="auth-error" className="font-mono text-[12px] text-exclude border border-exclude/40 bg-exclude/10 px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              data-testid="auth-submit-button"
              disabled={loading}
              className="w-full bg-keep text-black font-mono text-sm font-semibold py-2.5 hover:bg-keep/90 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              {mode === "login" ? "AUTHENTICATE" : "CREATE ACCOUNT"}
            </button>
          </form>
        </div>

        <div className="flex items-center gap-2 mt-4 font-mono text-[10px] text-warn tracking-wider">
          <ShieldOff size={12} /> NO REAL ORDERS · allow_real_live = false
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, testId, type = "text", placeholder }) {
  return (
    <label className="block">
      <span className="font-mono text-[10px] text-term-muted tracking-widest">{label}</span>
      <input
        data-testid={testId}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        required
        className="mt-1 w-full bg-term-bg border border-term-border px-3 py-2 font-mono text-sm text-term-text outline-none focus:border-keep transition-colors"
      />
    </label>
  );
}
