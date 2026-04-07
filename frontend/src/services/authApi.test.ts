import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "./authApi";

const originalFetch = globalThis.fetch;

function mockJsonErrorResponse(status: number, message: string, data?: unknown) {
  return {
    ok: false,
    status,
    json: async () => ({
      code: status,
      message,
      data,
    }),
  } as Response;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("authApi", () => {
  it("registers an account without expecting an auth session payload", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          user_id: "user_123",
          email: "learner@example.com",
          nickname: "Echo Learner",
        },
      }),
    }) as typeof fetch;

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "secret123",
      }),
    ).resolves.toBeUndefined();

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "secret123",
      }),
    });
  });

  it("logs in with credentials included and maps the backend auth session", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          access_token: "access-token-1",
          user: {
            user_id: "user_123",
            email: "learner@example.com",
            nickname: "Echo Learner",
          },
        },
      }),
    }) as typeof fetch;

    const result = await authApi.login({
      email: "learner@example.com",
      password: "secret123",
    });

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        email: "learner@example.com",
        password: "secret123",
      }),
    });
    expect(result).toEqual({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });
  });

  it("maps invalid login credentials to a localized error message", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockJsonErrorResponse(401, "Invalid email or password")) as typeof fetch;

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "wrong-pass",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "邮箱/密码错误",
    });
  });

  it("maps login validation details for invalid email format", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockJsonErrorResponse(400, "Validation error", [
        {
          type: "value_error",
          loc: ["body", "email"],
          msg: "Value error, Invalid email format",
        },
      ]),
    ) as typeof fetch;

    await expect(
      authApi.login({
        email: "not-an-email",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "邮箱格式错误",
    });
  });

  it("maps login validation details for password rules", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "password"],
            msg: "Value error, Password must be at least 8 characters",
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "password"],
            msg: "Value error, Password must include letters and numbers",
          },
        ]),
      ) as typeof fetch;

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "short",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "密码至少 8 位且需包含字母和数字",
    });

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "password",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "密码至少 8 位且需包含字母和数字",
    });
  });

  it("maps pending verification and rate-limit login errors to localized messages", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        mockJsonErrorResponse(403, "Please verify your email before logging in"),
      )
      .mockResolvedValueOnce(
        mockJsonErrorResponse(429, "Too many login attempts. Please try again later."),
      ) as typeof fetch;

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "请先完成邮箱验证后再登录",
    });

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "登录尝试次数过多，请稍后再试",
    });
  });

  it("maps register duplicate-email, validation, and rate-limit errors to localized messages", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(mockJsonErrorResponse(400, "Email already registered"))
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "email"],
            msg: "Value error, Invalid email format",
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "password"],
            msg: "Value error, Password must include letters and numbers",
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonErrorResponse(429, "Too many registration attempts. Please try again later."),
      ) as typeof fetch;

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "该邮箱已被注册",
    });

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "not-an-email",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "邮箱格式错误",
    });

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "password",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "密码至少 8 位且需包含字母和数字",
    });

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "注册尝试次数过多，请稍后再试",
    });
  });

  it("uses localized login/register fallbacks for unknown validation details", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "email"],
            msg: "Value error, Some new validation rule",
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonErrorResponse(400, "Validation error", [
          {
            type: "value_error",
            loc: ["body", "nickname"],
            msg: "Value error, Some new validation rule",
          },
        ]),
      ) as typeof fetch;

    await expect(
      authApi.login({
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "登录信息格式有误，请检查后重试。",
    });

    await expect(
      authApi.register({
        nickname: "Echo Learner",
        email: "learner@example.com",
        password: "secret123",
      }),
    ).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "注册信息格式有误，请检查后重试。",
    });
  });

  it("refreshes the auth session from cookie-backed credentials", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          access_token: "access-token-2",
          user: {
            user_id: "user_123",
            email: "learner@example.com",
            nickname: "Echo Learner",
          },
        },
      }),
    }) as typeof fetch;

    const result = await authApi.refresh();

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    expect(result.accessToken).toBe("access-token-2");
    expect(result.user.userId).toBe("user_123");
  });

  it("throws when logout returns a non-success status", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
    }) as typeof fetch;

    await expect(authApi.logout()).rejects.toMatchObject({
      code: "AUTH_API_FAILED",
      message: "退出登录失败。",
    });

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
    });
  });

  it("posts resend verification requests with credentials included", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
    }) as typeof fetch;

    await expect(authApi.resendVerification({ email: "learner@example.com" })).resolves.toBeUndefined();

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/resend-verification", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email: "learner@example.com" }),
    });
  });

  it("posts verify email tokens with credentials included", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
    }) as typeof fetch;

    await expect(authApi.verifyEmail("verify-token")).resolves.toBeUndefined();

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ token: "verify-token" }),
    });
  });

  it("posts password recovery and reset requests with credentials included", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      }) as typeof fetch;

    await expect(authApi.forgotPassword({ email: "learner@example.com" })).resolves.toBeUndefined();
    await expect(
      authApi.resetPassword({
        token: "reset-token",
        password: "renew1234",
      }),
    ).resolves.toBeUndefined();

    expect(globalThis.fetch).toHaveBeenNthCalledWith(1, "/api/v1/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email: "learner@example.com" }),
    });
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, "/api/v1/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        token: "reset-token",
        password: "renew1234",
      }),
    });
  });
});
