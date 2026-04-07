import { afterEach, describe, expect, it, vi } from "vitest";

import * as mockApi from "./mockApi";
import { createPracticeSession } from "./practiceApi";
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
});
