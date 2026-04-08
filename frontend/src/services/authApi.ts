import type {
  AppError,
  AuthCredentials,
  AuthSession,
  AuthUser,
  EmailPayload,
  RegisterPayload,
  ResetPasswordPayload,
} from "../types/app";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type ValidationErrorDetail = {
  loc?: unknown;
  msg?: string;
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

function findValidationMessage(data: unknown): string | null {
  if (!Array.isArray(data)) {
    return null;
  }

  const detail = data.find((item): item is ValidationErrorDetail => {
    return typeof item === "object" && item !== null && "msg" in item;
  });
  return detail?.msg ?? null;
}

function translateValidationMessage(message: string): string | null {
  if (message.includes("Invalid email format")) {
    return "邮箱格式错误";
  }

  if (
    message.includes("Password must be at least 8 characters") ||
    message.includes("Password must include letters and numbers")
  ) {
    return "密码至少 8 位且需包含字母和数字";
  }

  if (message.includes("Nickname is required")) {
    return "昵称不能为空";
  }

  return null;
}

function translateAuthMessage(
  message: string,
  data?: unknown,
  action?: "login" | "register",
): string {
  const exactTranslations: Record<string, string> = {
    "Invalid email or password": "邮箱/密码错误",
    "Please verify your email before logging in": "请先完成邮箱验证后再登录",
    "Password reset link is invalid or expired": "重置链接已失效或已过期，请重新申请。",
    "Email already registered": "该邮箱已被注册",
    "Too many login attempts. Please try again later.": "登录尝试次数过多，请稍后再试",
    "Too many registration attempts. Please try again later.": "注册尝试次数过多，请稍后再试",
  };

  const translatedMessage = exactTranslations[message];
  if (translatedMessage) {
    return translatedMessage;
  }

  if (message === "Validation error") {
    const detailMessage = findValidationMessage(data);
    if (detailMessage) {
      const translatedDetail = translateValidationMessage(detailMessage);
      if (translatedDetail) {
        return translatedDetail;
      }
    }

    if (action === "login") {
      return "登录信息格式有误，请检查后重试。";
    }

    if (action === "register") {
      return "注册信息格式有误，请检查后重试。";
    }
  }

  return message;
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
  action?: "login" | "register",
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
    throw toError(translateAuthMessage(payload.message ?? fallbackMessage, payload.data, action));
  }
  return payload.data as T;
}

async function parseAuthResponse(
  input: string,
  init: RequestInit,
  fallbackMessage: string,
  action?: "login" | "register",
): Promise<AuthSession> {
  const payload = await parseResponse<BackendAuthSession>(input, init, fallbackMessage, action);
  return toAuthSession(payload);
}

async function expectNoContent(
  input: string,
  init: RequestInit,
  fallbackMessage: string,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      credentials: "include",
    });
  } catch {
    throw toError(fallbackMessage);
  }

  if (!response.ok) {
    if (response.headers?.get("content-type")?.includes("application/json")) {
      const payload = (await response.json()) as ApiResponse<unknown>;
      throw toError(translateAuthMessage(payload.message ?? fallbackMessage));
    }
    throw toError(fallbackMessage);
  }
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
    "login",
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
    "register",
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
  await expectNoContent("/api/v1/auth/logout", { method: "POST" }, "退出登录失败。");
}

export async function resendVerification(payload: EmailPayload): Promise<void> {
  await expectNoContent(
    "/api/v1/auth/resend-verification",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "验证邮件发送失败，请稍后重试。",
  );
}

export async function verifyEmail(token: string): Promise<void> {
  await expectNoContent(
    "/api/v1/auth/verify-email",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    },
    "邮箱验证失败，请稍后重试。",
  );
}

export async function forgotPassword(payload: EmailPayload): Promise<void> {
  await expectNoContent(
    "/api/v1/auth/forgot-password",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "密码找回请求失败，请稍后重试。",
  );
}

export async function resetPassword(payload: ResetPasswordPayload): Promise<void> {
  await expectNoContent(
    "/api/v1/auth/reset-password",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "密码重置失败，请稍后重试。",
  );
}
