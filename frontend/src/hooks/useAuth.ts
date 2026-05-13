import { useCallback, useEffect, useState } from "react";
import { getMe, type User } from "../api/auth";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await getMe();
      setUser(res.data);
    } catch {
      localStorage.removeItem("token");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 마운트 시 인증 상태 확인 → setUser/setLoading (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkAuth();
  }, [checkAuth]);

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    window.location.href = "/login";
  };

  return { user, loading, logout, checkAuth };
}
