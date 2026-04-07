import {
  createContext,
  startTransition,
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

  function applyAuthenticatedState(session: AuthSession) {
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
  }

  function applyAnonymousState() {
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
  }

  async function refreshSession() {
    const session = await refreshRequest();
    return applyAuthenticatedState(session);
  }

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
  }, []);

  async function login(credentials: AuthCredentials): Promise<AuthSession> {
    const session = await loginRequest(credentials);
    applyAuthenticatedState(session);
    return session;
  }

  async function register(payload: RegisterPayload): Promise<void> {
    await registerRequest(payload);
  }

  async function logout() {
    await logoutRequest();
    applyAnonymousState();
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      register,
      logout,
    }),
    [state],
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
