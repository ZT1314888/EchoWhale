import type { AppError, AuthCredentials, AuthSession, AuthUser, RegisterPayload } from "../types/app";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type BackendAuthUser = {
  user_id: string;
  email: string;
  nickname: string;
};

type BackendAuthSession = {
  access_token: string;
  user: BackendAuthUser;
};

type BackendRegisterResponse = {
  user_id: string;
  email: string;
  nickname: string;
};

function toError(message: string, code = "AUTH_API_FAILED"): AppError {
  return { code, message };
}

function toAuthUser(user: BackendAuthUser): AuthUser {
  return {
    userId: user.user_id,
    email: user.email,
    nickname: user.nickname,
  };
}

function toAuthSession(payload: BackendAuthSession): AuthSession {
  return {
    accessToken: payload.access_token,
    user: toAuthUser(payload.user),
  };
}

async function parseResponse<T>(
  input: string,
  init: RequestInit,
  fallbackMessage: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      credentials: "include",
    });
  } catch {
    throw toError(fallbackMessage);
  }

  const payload = (await response.json()) as ApiResponse<T>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? fallbackMessage);
  }
  return payload.data as T;
}

async function parseAuthResponse(
  input: string,
  init: RequestInit,
  fallbackMessage: string,
): Promise<AuthSession> {
  const payload = await parseResponse<BackendAuthSession>(input, init, fallbackMessage);
  return toAuthSession(payload);
}

export async function login(credentials: AuthCredentials): Promise<AuthSession> {
  return parseAuthResponse(
    "/api/v1/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    },
    "登录失败，请稍后重试。",
  );
}

export async function register(payload: RegisterPayload): Promise<void> {
  await parseResponse<BackendRegisterResponse>(
    "/api/v1/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "注册失败，请稍后重试。",
  );
}

export async function refresh(): Promise<AuthSession> {
  return parseAuthResponse(
    "/api/v1/auth/refresh",
    { method: "POST" },
    "登录状态恢复失败。",
  );
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
    });
  } catch {
    throw toError("退出登录失败。");
  }
}
