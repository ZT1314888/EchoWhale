import { afterEach, describe, expect, it, vi } from "vitest";

import * as mockApi from "./mockApi";
import { createPracticeSession, getPracticeSession, submitPracticeTurn } from "./practiceApi";
import * as sessionApi from "./sessionApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("practiceApi", () => {
  it("creates sample sessions through the real backend session api", async () => {
    const createSampleSpy = vi
      .spyOn(sessionApi, "createSamplePracticeSession")
      .mockResolvedValue({ sessionId: "sess_sample" });
    const mockCreateSpy = vi.spyOn(mockApi, "createPracticeSession");

    const result = await createPracticeSession({
      source: "sample",
      sampleSceneId: "coffee",
    });

    expect(result).toEqual({ sessionId: "sess_sample" });
    expect(createSampleSpy).toHaveBeenCalledWith("coffee");
    expect(mockCreateSpy).not.toHaveBeenCalled();
  });

  it("loads session details through the real backend session api for any session id", async () => {
    const session = {
      id: "session-coffee",
      title: "咖啡店柜台点单",
      roleLabel: "角色 · barista",
      openingPrompt: "开场提示：Hi there, what can I get started for you today?",
      tags: ["coffee"],
      liveHint: "先用一句短句回应，再补一条细节，会更稳。",
      voiceTitle: "点一下，用声音回答",
      voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
      messages: [],
    };
    const getSessionSpy = vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(session);
    const mockGetSpy = vi.spyOn(mockApi, "getPracticeSession");

    const result = await getPracticeSession("session-coffee");

    expect(result).toEqual(session);
    expect(getSessionSpy).toHaveBeenCalledWith("session-coffee");
    expect(mockGetSpy).not.toHaveBeenCalled();
  });

  it("submits practice turns through the real backend session api for any session id", async () => {
    const turnResult = {
      messages: [
        {
          id: "msg_1",
          role: "coach" as const,
          label: "教练 · 追问",
          content: "Hi there, what can I get started for you today?",
        },
      ],
      feedback: {
        grammar: { title: "Grammar", body: "Your meaning is clear." },
        moreNatural: { title: "More Natural", body: "Could I get an iced latte, please?" },
        usefulWords: {
          title: "Useful Words",
          words: ["latte"],
          body: "把这些词带进下一轮回答，会更自然。",
        },
        nextStep: {
          title: "Next Step",
          body: "下一轮试着在一句主回应后再补一句细节。",
        },
      },
    };
    const submitSpy = vi.spyOn(sessionApi, "submitPracticeTurn").mockResolvedValue(turnResult);
    const mockSubmitSpy = vi.spyOn(mockApi, "submitPracticeTurn");

    const result = await submitPracticeTurn("session-coffee", {
      content: "Could I get an iced latte, please?",
    });

    expect(result).toEqual(turnResult);
    expect(submitSpy).toHaveBeenCalledWith("session-coffee", {
      content: "Could I get an iced latte, please?",
    });
    expect(mockSubmitSpy).not.toHaveBeenCalled();
  });
});
