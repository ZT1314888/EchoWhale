import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "./authApi";

const originalFetch = globalThis.fetch;

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
});
