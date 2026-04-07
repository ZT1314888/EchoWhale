import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../services/authApi";
import { apiFetch } from "../services/apiClient";
import { AuthProvider, useAuth } from "./AuthProvider";

const originalFetch = globalThis.fetch;

function apiJsonResponse(status: number, data?: unknown, message = "Success") {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({
      code: status,
      message,
      data,
    }),
  } as Response;
}

function ProtectedProbe() {
  const auth = useAuth();
  const [requestStatus, setRequestStatus] = useState("idle");

  useEffect(() => {
    let active = true;

    apiFetch("/api/v1/protected")
      .then((response) => {
        if (active) {
          setRequestStatus(String(response.status));
        }
      })
      .catch(() => {
        if (active) {
          setRequestStatus("error");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div>
      <span data-testid="auth-status">{auth.status}</span>
      <span data-testid="request-status">{requestStatus}</span>
    </div>
  );
}

describe("AuthProvider", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("retries protected requests after runtime token refresh and keeps the user authenticated", async () => {
    vi.spyOn(authApi, "refresh")
      .mockResolvedValueOnce({
        accessToken: "access-token-1",
        user: {
          userId: "user_123",
          email: "learner@example.com",
          nickname: "Echo Learner",
        },
      })
      .mockResolvedValueOnce({
        accessToken: "access-token-2",
        user: {
          userId: "user_123",
          email: "learner@example.com",
          nickname: "Echo Learner",
        },
      });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(apiJsonResponse(401, undefined, "Authentication required"))
      .mockResolvedValueOnce(apiJsonResponse(200, { ok: true })) as typeof fetch;

    await act(async () => {
      render(
        <AuthProvider>
          <ProtectedProbe />
        </AuthProvider>,
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
      expect(screen.getByTestId("request-status")).toHaveTextContent("200");
      expect(authApi.refresh).toHaveBeenCalledTimes(2);
    });
  });

  it("returns to anonymous state when runtime token refresh fails", async () => {
    vi.spyOn(authApi, "refresh")
      .mockResolvedValueOnce({
        accessToken: "access-token-1",
        user: {
          userId: "user_123",
          email: "learner@example.com",
          nickname: "Echo Learner",
        },
      })
      .mockRejectedValueOnce({
        code: "AUTH_REQUIRED",
        message: "Authentication required",
      });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(apiJsonResponse(401, undefined, "Authentication required")) as typeof fetch;

    await act(async () => {
      render(
        <AuthProvider>
          <ProtectedProbe />
        </AuthProvider>,
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
      expect(screen.getByTestId("request-status")).toHaveTextContent("401");
      expect(authApi.refresh).toHaveBeenCalledTimes(2);
    });
  });
});
