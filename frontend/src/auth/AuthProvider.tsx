import {
  createContext,
  startTransition,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { AuthCredentials, AuthSession, AuthState, RegisterPayload } from "../types/app";
import { login as loginRequest, logout as logoutRequest, refresh, register as registerRequest } from "../services/authApi";
import { setAccessToken } from "../services/apiClient";

type AuthContextValue = AuthState & {
  login: (credentials: AuthCredentials) => Promise<AuthSession>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: "refreshing",
    user: null,
  });

  useEffect(() => {
    let active = true;

    refresh()
      .then((session) => {
        if (!active) {
          return;
        }
        setAccessToken(session.accessToken);
        startTransition(() => {
          setState({
            status: "authenticated",
            user: session.user,
          });
        });
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setAccessToken(null);
        startTransition(() => {
          setState({
            status: "anonymous",
            user: null,
          });
        });
      });

    return () => {
      active = false;
    };
  }, []);

  async function login(credentials: AuthCredentials): Promise<AuthSession> {
    const session = await loginRequest(credentials);
    setAccessToken(session.accessToken);
    setState({
      status: "authenticated",
      user: session.user,
    });
    return session;
  }

  async function register(payload: RegisterPayload): Promise<void> {
    await registerRequest(payload);
  }

  async function logout() {
    await logoutRequest();
    setAccessToken(null);
    setState({
      status: "anonymous",
      user: null,
    });
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
