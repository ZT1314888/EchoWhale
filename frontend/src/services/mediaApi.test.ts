import { afterEach, describe, expect, it, vi } from "vitest";

import { uploadMedia } from "./mediaApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
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
});
