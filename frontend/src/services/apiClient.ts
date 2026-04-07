let accessToken: string | null = null;
let refreshSessionHandler: (() => Promise<string>) | null = null;
let authFailureHandler: (() => void) | null = null;
let activeRefresh: Promise<string> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function configureApiClientAuth(handlers: {
  refreshSession: () => Promise<string>;
  handleAuthFailure: () => void;
}) {
  refreshSessionHandler = handlers.refreshSession;
  authFailureHandler = handlers.handleAuthFailure;
}

export function resetApiClientAuth() {
  accessToken = null;
  refreshSessionHandler = null;
  authFailureHandler = null;
  activeRefresh = null;
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const request = {
    ...init,
    headers,
    credentials: "include",
  };

  const response = await fetch(input, request);
  if (response.status !== 401 || !refreshSessionHandler) {
    return response;
  }

  try {
    const rotatedToken = await getRefreshSession();
    const retryHeaders = new Headers(init.headers);
    retryHeaders.set("Authorization", `Bearer ${rotatedToken}`);
    return fetch(input, {
      ...init,
      headers: retryHeaders,
      credentials: "include",
    });
  } catch {
    authFailureHandler?.();
    return response;
  }
}

async function getRefreshSession() {
  if (!activeRefresh) {
    activeRefresh = refreshSessionHandler!().finally(() => {
      activeRefresh = null;
    });
  }
  return activeRefresh;
}
