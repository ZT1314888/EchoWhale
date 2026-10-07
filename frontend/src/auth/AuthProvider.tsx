import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { AuthCredentials, AuthSession, AuthState, RegisterPayload } from "../types/app";
import {
  login as loginRequest,
  logout as logoutRequest,
  refresh as refreshRequest,
  register as registerRequest,
} from "../services/authApi";
import { configureApiClientAuth, resetApiClientAuth, setAccessToken } from "../services/apiClient";

type AuthContextValue = AuthState & {
  login: (credentials: AuthCredentials) => Promise<AuthSession>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const isMountedRef = useRef(true);
  const [state, setState] = useState<AuthState>({
    status: "refreshing",
    user: null,
  });

  // 回调链整体 useCallback 稳定化：挂载 effect 与 context value 的 memo 都依赖
  // 这些函数，稳定身份让 exhaustive-deps 可以如实声明依赖而不引入重复执行。
  // 捕获项只有 setState（恒稳定）与 isMountedRef（ref 对象恒稳定），依赖列为空是安全的。
  const applyAuthenticatedState = useCallback((session: AuthSession) => {
    setAccessToken(session.accessToken);
    if (!isMountedRef.current) {
      return session.accessToken;
    }
    startTransition(() => {
      setState({
        status: "authenticated",
        user: session.user,
      });
    });
    return session.accessToken;
  }, []);

  const applyAnonymousState = useCallback(() => {
    setAccessToken(null);
    if (!isMountedRef.current) {
      return;
    }
    startTransition(() => {
      setState({
        status: "anonymous",
        user: null,
      });
    });
  }, []);

  const refreshSession = useCallback(async () => {
    const session = await refreshRequest();
    return applyAuthenticatedState(session);
  }, [applyAuthenticatedState]);

  useEffect(() => {
    isMountedRef.current = true;
    configureApiClientAuth({
      refreshSession,
      handleAuthFailure: applyAnonymousState,
    });

    refreshSession().catch(() => {
      applyAnonymousState();
    });

    return () => {
      isMountedRef.current = false;
      resetApiClientAuth();
    };
  }, [refreshSession, applyAnonymousState]);

  const login = useCallback(
    async (credentials: AuthCredentials): Promise<AuthSession> => {
      const session = await loginRequest(credentials);
      applyAuthenticatedState(session);
      return session;
    },
    [applyAuthenticatedState],
  );

  const register = useCallback(async (payload: RegisterPayload): Promise<void> => {
    await registerRequest(payload);
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    applyAnonymousState();
  }, [applyAnonymousState]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      register,
      logout,
    }),
    [state, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
