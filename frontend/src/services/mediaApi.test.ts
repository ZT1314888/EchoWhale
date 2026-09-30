import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SCENE_ANALYSIS_POLL_INTERVAL_MS,
  SCENE_ANALYSIS_POLL_TIMEOUT_MS,
  getSceneAnalysisStatus,
  uploadMedia,
  waitForSceneAnalysis,
} from "./mediaApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("mediaApi", () => {
  it("uploads a file and returns the backend media contract", async () => {
    const file = new File(["hello"], "coffee.png", { type: "image/png" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          media_id: "med_123",
          filename: "coffee.png",
          content_type: "image/png",
          file_size: 5,
          storage_key: "media/demo-user/2026/04/01/med_123-coffee.png",
          preview_url: "https://signed.test/media/demo-user/2026/04/01/med_123-coffee.png?signature=demo",
          preview_url_expires_at: "2026-04-02T12:00:00Z",
          upload_status: "uploaded",
        },
      }),
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const result = await uploadMedia(file);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/media/upload");
    expect(options?.method).toBe("POST");
    expect(options?.body).toBeInstanceOf(FormData);
    expect(result).toMatchObject({
      mediaId: "med_123",
      previewUrl: "https://signed.test/media/demo-user/2026/04/01/med_123-coffee.png?signature=demo",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
  });

  it("maps backend validation errors to a user-facing message", async () => {
    const file = new File(["hello"], "bad.txt", { type: "text/plain" });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 415,
      json: async () => ({
        code: 1001,
        message: "Unsupported media type: text/plain",
      }),
    }) as typeof fetch;

    await expect(uploadMedia(file)).rejects.toMatchObject({
      code: "UPLOAD_FAILED",
      message: "Unsupported media type: text/plain",
    });
  });

  it("maps the scene-analysis status payload into the frontend contract", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          media_id: "med_1",
          status: "ready",
          prompt_version: "v1",
          scene: "coffee_shop",
          role: "barista",
          confidence: 0.92,
        },
      }),
    }) as typeof fetch;

    await expect(getSceneAnalysisStatus("med_1")).resolves.toEqual({
      mediaId: "med_1",
      status: "ready",
      promptVersion: "v1",
      scene: "coffee_shop",
      role: "barista",
      confidence: 0.92,
      errorCode: undefined,
    });
  });

  it("polls scene analysis on an interval until it reports ready", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 200,
          message: "Success",
          data: { media_id: "med_1", status: "pending" },
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          code: 200,
          message: "Success",
          data: { media_id: "med_1", status: "ready" },
        }),
      });
    globalThis.fetch = fetchMock as typeof fetch;

    const pending = waitForSceneAnalysis("med_1");
    await vi.advanceTimersByTimeAsync(SCENE_ANALYSIS_POLL_INTERVAL_MS * 2);

    await expect(pending).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("maps a failed analysis with the unsupported-image code to the localized error", async () => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: { media_id: "med_bad", status: "failed", error_code: 1007 },
      }),
    }) as typeof fetch;

    const pending = waitForSceneAnalysis("med_bad");
    const expectation = expect(pending).rejects.toMatchObject({
      code: "UNSUPPORTED_SCENE_IMAGE",
    });
    await vi.advanceTimersByTimeAsync(SCENE_ANALYSIS_POLL_INTERVAL_MS * 2);
    await expectation;
  });

  it("times out when scene analysis never becomes ready", async () => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: { media_id: "med_slow", status: "pending" },
      }),
    }) as typeof fetch;

    const pending = waitForSceneAnalysis("med_slow");
    const expectation = expect(pending).rejects.toMatchObject({
      code: "SCENE_ANALYSIS_TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(
      SCENE_ANALYSIS_POLL_TIMEOUT_MS + SCENE_ANALYSIS_POLL_INTERVAL_MS,
    );
    await expectation;
  });
});
