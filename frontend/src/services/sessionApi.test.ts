import { afterEach, describe, expect, it, vi } from "vitest";

import { createPracticeSession, getPracticeSession, submitPracticeTurn } from "./sessionApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("sessionApi", () => {
  it("starts a practice session from a media id", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session_id: "sess_123",
          media_id: "med_123",
          scene: "coffee_shop",
          role: "barista",
          opener: "Hi there, what can I get started for you today?",
          status: "active",
          labels: ["coffee", "menu"],
          messages: [],
        },
      }),
    }) as typeof fetch;

    const result = await createPracticeSession("med_123");

    expect(result).toEqual({ sessionId: "sess_123" });
  });

  it("maps a backend session snapshot into the frontend session summary", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session_id: "sess_123",
          media_id: "med_123",
          scene: "coffee_shop",
          role: "barista",
          opener: "Hi there, what can I get started for you today?",
          status: "active",
          labels: ["coffee", "menu"],
          messages: [
            {
              message_id: "msg_1",
              role: "assistant",
              text: "Hi there, what can I get started for you today?",
            },
          ],
        },
      }),
    }) as typeof fetch;

    const session = await getPracticeSession("sess_123");

    expect(session.title).toBe("咖啡店柜台点单");
    expect(session.roleLabel).toContain("barista");
    expect(session.openingPrompt).toContain("Hi there");
    expect(session.messages).toEqual([
      {
        id: "msg_1",
        role: "coach",
        label: "教练 · 追问",
        content: "Hi there, what can I get started for you today?",
      },
    ]);
  });

  it("maps a reply response into frontend messages and feedback", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session: {
            session_id: "sess_123",
            media_id: "med_123",
            scene: "coffee_shop",
            role: "barista",
            opener: "Hi there, what can I get started for you today?",
            status: "active",
            labels: ["coffee", "menu"],
            messages: [
              {
                message_id: "msg_1",
                role: "assistant",
                text: "Hi there, what can I get started for you today?",
              },
              {
                message_id: "msg_2",
                role: "user",
                text: "Could I get an iced latte, please?",
              },
              {
                message_id: "msg_3",
                role: "assistant",
                text: "Sure. What size would you like?",
                feedback: {
                  grammar: "Your meaning is clear.",
                  more_natural: "Could I get an iced latte, please?",
                  useful_words: ["latte", "size", "iced"],
                },
              },
            ],
          },
          feedback: {
            grammar: "Your meaning is clear.",
            more_natural: "Could I get an iced latte, please?",
            useful_words: ["latte", "size", "iced"],
          },
        },
      }),
    }) as typeof fetch;

    const result = await submitPracticeTurn("sess_123", {
      content: "Could I get an iced latte, please?",
    });

    expect(result.messages).toHaveLength(3);
    expect(result.feedback.grammar.body).toBe("Your meaning is clear.");
    expect(result.feedback.usefulWords.words).toEqual(["latte", "size", "iced"]);
  });
});