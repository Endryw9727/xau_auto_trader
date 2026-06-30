import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  // null = checking, false = unauthenticated, object = authenticated
  const [user, setUser] = useState(null);

  useEffect(() => {
    // Session lives in an httpOnly cookie; ask the backend who we are.
    api
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => setUser(false));
  }, []);

  const value = useMemo(() => {
    const login = async (email, password) => {
      const { data } = await api.post("/auth/login", { email, password });
      setUser(data.user);
    };
    const register = async (email, password, name) => {
      const { data } = await api.post("/auth/register", { email, password, name });
      setUser(data.user);
    };
    const logout = async () => {
      try {
        await api.post("/auth/logout");
      } catch (e) {
        // ignore network errors on logout
      }
      setUser(false);
    };
    return { user, login, register, logout };
  }, [user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
