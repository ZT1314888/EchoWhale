import { afterEach, describe, expect, it, vi } from "vitest";

import * as learnerApi from "./learnerApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("learnerApi", () => {
  it("maps the backend profile payload into camelCase overview data", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          cefr_estimate: "B1",
          error_types: [
            { category: "tense", label: "时态", count: 12 },
            { category: "word_choice", label: "用词", count: 7 },
          ],
          scenes: [
            { scene_title: "咖啡店柜台点单", count: 8 },
            { scene_title: "街头出行与问路", count: 3 },
          ],
          practiced_turn_count: 23,
          updated_at: "2026-10-06 15:20",
        },
      }),
    }) as typeof fetch;

    const profile = await learnerApi.getLearnerProfile();

    expect(profile).toEqual({
      cefrEstimate: "B1",
      errorTypes: [
        { category: "tense", label: "时态", count: 12 },
        { category: "word_choice", label: "用词", count: 7 },
      ],
      scenes: [
        { sceneTitle: "咖啡店柜台点单", count: 8 },
        { sceneTitle: "街头出行与问路", count: 3 },
      ],
      practicedTurnCount: 23,
      updatedAt: "2026-10-06 15:20",
    });
  });

  it("maps the empty profile payload into null and empty collections", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          cefr_estimate: null,
          error_types: [],
          scenes: [],
          practiced_turn_count: 0,
          updated_at: null,
        },
      }),
    }) as typeof fetch;

    const profile = await learnerApi.getLearnerProfile();

    expect(profile).toEqual({
      cefrEstimate: null,
      errorTypes: [],
      scenes: [],
      practicedTurnCount: 0,
      updatedAt: null,
    });
  });

  it("throws a localized error when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({
        code: 5000,
        message: "Internal server error",
        data: null,
      }),
    }) as typeof fetch;

    // 与 historyApi 惯例一致：信封自带 message 时透传，本地中文文案作兜底。
    await expect(learnerApi.getLearnerProfile()).rejects.toEqual({
      code: "LEARNER_API_FAILED",
      message: "Internal server error",
    });
  });

  it("falls back to the localized message when the error envelope has no message", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({
        code: 5000,
        message: null,
        data: null,
      }),
    }) as typeof fetch;

    await expect(learnerApi.getLearnerProfile()).rejects.toEqual({
      code: "LEARNER_API_FAILED",
      message: "学习进度加载失败。",
    });
  });

  it("throws a localized error when the request is rejected", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network down")) as typeof fetch;

    await expect(learnerApi.getLearnerProfile()).rejects.toEqual({
      code: "LEARNER_API_FAILED",
      message: "学习进度加载失败。",
    });
  });
});
