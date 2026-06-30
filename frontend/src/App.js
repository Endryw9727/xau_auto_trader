import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Data from "@/pages/Data";
import EdgeLab from "@/pages/EdgeLab";
import SignificanceAudit from "@/pages/SignificanceAudit";
import BotDiagnostics from "@/pages/BotDiagnostics";
import AIResearch from "@/pages/AIResearch";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null)
    return (
      <div className="h-full flex items-center justify-center bg-term-bg">
        <span className="font-mono text-term-muted text-sm animate-blink">LOADING CONSOLE…</span>
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route path="/" element={<Navigate to="/significance-audit" replace />} />
            <Route path="/significance-audit" element={<SignificanceAudit />} />
            <Route path="/edge-lab" element={<EdgeLab />} />
            <Route path="/data" element={<Data />} />
            <Route path="/bot-diagnostics" element={<BotDiagnostics />} />
            <Route path="/ai-research" element={<AIResearch />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" />
    </AuthProvider>
  );
}

export default App;
