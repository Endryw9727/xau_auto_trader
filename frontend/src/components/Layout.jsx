import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  Gavel, FlaskConical, Database, Bot, BrainCircuit, LogOut, Terminal, Wifi, WifiOff,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import SafetyBanner from "@/components/SafetyBanner";
import api from "@/lib/api";

const NAV = [
  { to: "/significance-audit", label: "Significance Audit", icon: Gavel, tag: "VERDICT", testId: "nav-significance-audit" },
  { to: "/edge-lab", label: "Edge Lab", icon: FlaskConical, testId: "nav-edge-lab" },
  { to: "/data", label: "Data", icon: Database, testId: "nav-data" },
  { to: "/bot-diagnostics", label: "Bot Diagnostics", icon: Bot, testId: "nav-bot-diagnostics" },
  { to: "/ai-research", label: "AI Research", icon: BrainCircuit, testId: "nav-ai-research" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [safety, setSafety] = useState(null);

  useEffect(() => {
    api.get("/safety").then((r) => setSafety(r.data)).catch(() => {});
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="h-full flex flex-col bg-term-bg">
      <SafetyBanner />
      <div className="flex flex-1 min-h-0">
        <aside className="w-60 shrink-0 border-r border-term-border bg-term-surface flex flex-col">
          <div className="px-4 py-4 border-b border-term-border">
            <div className="flex items-center gap-2 text-keep">
              <Terminal size={18} strokeWidth={2} />
              <span className="font-mono font-semibold tracking-tight text-sm text-term-text">RESEARCH CONSOLE</span>
            </div>
            <p className="font-mono text-[10px] text-term-dim mt-1 tracking-wider">QUANT EDGE · v1.0</p>
          </div>

          <nav className="flex-1 py-2">
            {NAV.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={item.testId}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 px-4 py-2.5 text-sm border-l-2 transition-colors",
                      isActive
                        ? "border-keep bg-keep/5 text-term-text"
                        : "border-transparent text-term-muted hover:text-term-text hover:bg-term-surface2"
                    )
                  }
                >
                  <Icon size={16} strokeWidth={1.75} />
                  <span className="flex-1">{item.label}</span>
                  {item.tag && (
                    <span className="font-mono text-[9px] px-1 py-0.5 bg-keep/15 text-keep tracking-wider">
                      {item.tag}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>

          <div className="px-4 py-3 border-t border-term-border">
            <div className="flex items-center gap-2 mb-2 font-mono text-[10px] tracking-wider">
              {safety?.external_api ? (
                <span className="flex items-center gap-1 text-keep"><Wifi size={11} /> EXTERNAL API</span>
              ) : (
                <span className="flex items-center gap-1 text-term-dim"><WifiOff size={11} /> MOCK MODE</span>
              )}
            </div>
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="font-mono text-xs text-term-text truncate" data-testid="current-user">{user?.email}</div>
                <div className="font-mono text-[10px] text-term-dim uppercase">{user?.role}</div>
              </div>
              <button
                data-testid="logout-button"
                onClick={handleLogout}
                title="Logout"
                className="p-1.5 border border-term-border text-term-muted hover:text-exclude hover:border-exclude/60 transition-colors"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </aside>

        <main className="flex-1 min-w-0 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
