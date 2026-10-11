import { afterEach, describe, expect, it, vi } from "vitest";

import * as mediaApi from "./mediaApi";
import { createPracticeSession, getPracticeSession } from "./practiceApi";
import * as sessionApi from "./sessionApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("practiceApi", () => {
  it("creates sample sessions through the real backend session api", async () => {
    const createSampleSpy = vi
      .spyOn(sessionApi, "createSamplePracticeSession")
      .mockResolvedValue({ kind: "created", sessionId: "sess_sample" });

    const result = await createPracticeSession({
      source: "sample",
      sampleSceneId: "coffee",
    });

    expect(result).toEqual({ sessionId: "sess_sample" });
    expect(createSampleSpy).toHaveBeenCalledWith("coffee", undefined);
  });

  it("loads session details through the real backend session api for any session id", async () => {
    const session = {
      id: "session-coffee",
      title: "咖啡店柜台点单",
      roleLabel: "角色 · barista",
      openingPrompt: "开场提示：Hi there, what can I get started for you today?",
      status: "active",
      tags: ["coffee"],
      voiceTitle: "点一下，用声音回答",
      voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
      messages: [],
    };
    const getSessionSpy = vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(session);

    const result = await getPracticeSession("session-coffee");

    expect(result).toEqual(session);
    expect(getSessionSpy).toHaveBeenCalledWith("session-coffee");
  });

  it("waits for scene analysis and retries session start when the backend answers 202", async () => {
    const createMediaSpy = vi
      .spyOn(sessionApi, "createPracticeSession")
      .mockResolvedValueOnce({ kind: "analyzing", mediaId: "med_wait" })
      .mockResolvedValueOnce({ kind: "created", sessionId: "sess_wait" });
    const waitSpy = vi.spyOn(mediaApi, "waitForSceneAnalysis").mockResolvedValue(undefined);
    const onAnalysisPending = vi.fn();

    const result = await createPracticeSession(
      { source: "file", uploadedMedia: uploadedMedia("med_wait") },
      { onAnalysisPending },
    );

    expect(onAnalysisPending).toHaveBeenCalledTimes(1);
    expect(waitSpy).toHaveBeenCalled();
    expect(waitSpy.mock.calls[0]?.[0]).toBe("med_wait");
    expect(createMediaSpy).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ sessionId: "sess_wait" });
  });

  it("propagates structured analysis failures after a 202 pending response", async () => {
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({
      kind: "analyzing",
      mediaId: "med_failed",
    });
    vi.spyOn(mediaApi, "waitForSceneAnalysis").mockRejectedValue({
      code: "SCENE_ANALYSIS_FAILED",
      message: "图片场景分析失败，请重试或换一张图片。",
    });

    await expect(
      createPracticeSession({ source: "file", uploadedMedia: uploadedMedia("med_failed") }),
    ).rejects.toMatchObject({ code: "SCENE_ANALYSIS_FAILED" });
  });

  it("threads the abort signal and status callback through the analysis wait", async () => {
    const controller = new AbortController();
    const onStatus = vi.fn();
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({
      kind: "analyzing",
      mediaId: "med_signal",
    });
    const waitSpy = vi
      .spyOn(mediaApi, "waitForSceneAnalysis")
      .mockRejectedValue(Object.assign(new Error("aborted"), { name: "AbortError" }));

    await expect(
      createPracticeSession(
        { source: "file", uploadedMedia: uploadedMedia("med_signal") },
        { signal: controller.signal, onAnalysisStatus: onStatus },
      ),
    ).rejects.toMatchObject({ name: "AbortError" });

    expect(waitSpy.mock.calls[0]?.[0]).toBe("med_signal");
    expect(waitSpy.mock.calls[0]?.[1]).toMatchObject({
      signal: controller.signal,
      onStatus,
    });
  });

});

function uploadedMedia(mediaId: string) {
  return {
    mediaId,
    filename: "coffee.png",
    contentType: "image/png",
    fileSize: 5,
    storageKey: `media/demo-user/${mediaId}-coffee.png`,
    previewUrl: "https://signed.test/preview",
    previewUrlExpiresAt: "2026-04-02T12:00:00Z",
    uploadStatus: "uploaded",
  };
}

