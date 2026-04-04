import { afterEach, describe, expect, it, vi } from "vitest";

import * as reviewApi from "./reviewApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("reviewApi", () => {
  it("maps a backend review snapshot into the frontend review summary", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session_id: "sess_123",
          title: "本轮回响",
          highlight: "你已经说清楚主要需求。",
          next_try: "下一轮再补一条细节。",
          feedback: {
            grammar: { title: "Grammar", body: "Your meaning is clear." },
            more_natural: {
              title: "More Natural",
              body: "Could I get an iced latte, please?",
            },
            useful_words: {
              title: "Useful Words",
              words: ["latte", "size", "iced"],
              body: "把这些词带进下一轮回答，会更自然。",
            },
            next_step: {
              title: "Next Step",
              body: "下一轮试着在一句主回应后再补一句细节。",
            },
          },
        },
      }),
    }) as typeof fetch;

    const review = await reviewApi.getPracticeReview("sess_123");

    expect(review.sessionId).toBe("sess_123");
    expect(review.title).toBe("本轮回响");
    expect(review.feedback.usefulWords.words).toEqual(["latte", "size", "iced"]);
  });
});
