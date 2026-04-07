import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiFetch,
  configureApiClientAuth,
  resetApiClientAuth,
  setAccessToken,
} from "./apiClient";

const originalFetch = globalThis.fetch;

function jsonResponse(status: number, data: unknown = { ok: true }) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response;
}

describe("apiClient", () => {
  beforeEach(() => {
    resetApiClientAuth();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    resetApiClientAuth();
  });

  it("refreshes once after a 401 response and retries the original request with the rotated token", async () => {
    setAccessToken("expired-token");
    const refreshSession = vi.fn().mockResolvedValue("rotated-token");
    configureApiClientAuth({
      refreshSession,
      handleAuthFailure: vi.fn(),
    });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true })) as typeof fetch;

    const response = await apiFetch("/api/v1/history/sessions");

    expect(response.status).toBe(200);
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).toHaveBeenNthCalledWith(
      1,
      "/api/v1/history/sessions",
      expect.objectContaining({
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(
      (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1]?.headers.get("Authorization"),
    ).toBe("Bearer expired-token");
    expect(
      (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[1][1]?.headers.get("Authorization"),
    ).toBe("Bearer rotated-token");
  });

  it("shares the same refresh request across concurrent 401 responses", async () => {
    let resolveRefresh: ((token: string) => void) | undefined;
    setAccessToken("expired-token");
    const refreshSession = vi.fn().mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          resolveRefresh = resolve;
        }),
    );

    configureApiClientAuth({
      refreshSession,
      handleAuthFailure: vi.fn(),
    });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401))
      .mockResolvedValueOnce(jsonResponse(401))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true })) as typeof fetch;

    const pendingA = apiFetch("/api/v1/history/sessions");
    const pendingB = apiFetch("/api/v1/history/sessions/sess_1");

    await Promise.resolve();
    resolveRefresh?.("rotated-token");

    const [responseA, responseB] = await Promise.all([pendingA, pendingB]);

    expect(responseA.status).toBe(200);
    expect(responseB.status).toBe(200);
    expect(refreshSession).toHaveBeenCalledTimes(1);
  });

  it("falls back to the original 401 response and clears auth state when refresh fails", async () => {
    setAccessToken("expired-token");
    const handleAuthFailure = vi.fn();
    configureApiClientAuth({
      refreshSession: vi.fn().mockRejectedValue(new Error("refresh failed")),
      handleAuthFailure,
    });

    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(401)) as typeof fetch;

    const response = await apiFetch("/api/v1/history/sessions");

    expect(response.status).toBe(401);
    expect(handleAuthFailure).toHaveBeenCalledTimes(1);
  });
});
