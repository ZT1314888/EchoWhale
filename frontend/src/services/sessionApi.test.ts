import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bootstrapVoiceSession,
  completeVoiceSession,
  createPracticeSession,
  createSamplePracticeSession,
  getPracticeSession,
  submitPracticeTurn,
} from "./sessionApi";

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

  it("starts a sample practice session from a sample scene id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session_id: "sess_sample",
          media_id: null,
          scene: "coffee_shop",
          role: "friendly barista",
          opener: "Hello! What would you like to order today?",
          status: "active",
          visual_anchors: ["counter", "pastry case"],
          vocab_candidates: ["latte", "size"],
          messages: [],
        },
      }),
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const result = await createSamplePracticeSession("coffee");

    expect(result).toEqual({ sessionId: "sess_sample" });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ sample_scene_id: "coffee" }),
      }),
    );
  });

  it("maps unsupported scene images to a localized frontend error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        code: 1007,
        message: "Unsupported scene image",
        data: {
          reason: "image_too_uniform",
          retryable: false,
        },
      }),
    }) as typeof fetch;

    await expect(createPracticeSession("med_black")).rejects.toEqual({
      code: "UNSUPPORTED_SCENE_IMAGE",
      message: "图片暂不支持这类内容，请换一张生活场景更清晰的图片。",
      reason: "image_too_uniform",
    });
  });

  it("maps temporary scene-analysis failures to a retryable frontend error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        code: 1008,
        message: "图片分析暂时不可用，请稍后重试。",
      }),
    }) as typeof fetch;

    await expect(createPracticeSession("med_503")).rejects.toEqual({
      code: "SCENE_ANALYSIS_UNAVAILABLE",
      message: "图片分析暂时不可用，请稍后重试。",
    });
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

  it("maps voice bootstrap into a frontend Deepgram session payload", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          session_id: "sess_123",
          deepgram_access_token: "dg-token",
          expires_in: 600,
          deepgram_ws_url: "wss://api.deepgram.com/v1/agent/converse",
          agent_settings: {
            type: "Settings",
            agent: {
              greeting: "Hi there, what can I get started for you today?",
            },
          },
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
            ],
          },
        },
      }),
    }) as typeof fetch;

    const result = await bootstrapVoiceSession("sess_123");

    expect(result.sessionId).toBe("sess_123");
    expect(result.deepgramAccessToken).toBe("dg-token");
    expect(result.deepgramWsUrl).toBe("wss://api.deepgram.com/v1/agent/converse");
    expect(result.agentSettings.type).toBe("Settings");
    expect(result.session.messages[0].content).toBe("Hi there, what can I get started for you today?");
  });

  it("maps voice completion into final session and review payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
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
            ],
          },
          review: {
            session_id: "sess_123",
            title: "本轮回响",
            highlight: "你已经说清楚主要需求。",
            next_try: "下一轮再补一条细节。",
            feedback: {
              grammar: { title: "Grammar", body: "Your meaning is clear." },
              more_natural: { title: "More Natural", body: "Could I get an iced latte, please?" },
              useful_words: {
                title: "Useful Words",
                words: ["latte", "size", "iced"],
                body: "把这些词带进下一轮回答，会更自然。",
              },
              next_step: { title: "Next Step", body: "下一轮试着在一句主回应后再补一句细节。" },
            },
          },
        },
      }),
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const result = await completeVoiceSession("sess_123", {
      conversation: [
        { role: "assistant", content: "Hi there, what can I get started for you today?" },
        { role: "user", content: "Could I get an iced latte, please?" },
      ],
      terminationReason: "user_ended",
      clientDiagnostics: {
        browser: "Edge 135",
        last_agent_event: "AgentAudioDone",
      },
    });

    expect(result.session.messages).toHaveLength(2);
    expect(result.review.title).toBe("本轮回响");
    expect(result.review.feedback.usefulWords.words).toEqual(["latte", "size", "iced"]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: JSON.stringify({
          conversation: [
            { role: "assistant", content: "Hi there, what can I get started for you today?" },
            { role: "user", content: "Could I get an iced latte, please?" },
          ],
          termination_reason: "user_ended",
          client_diagnostics: {
            browser: "Edge 135",
            last_agent_event: "AgentAudioDone",
          },
        }),
      }),
    );
  });
});
