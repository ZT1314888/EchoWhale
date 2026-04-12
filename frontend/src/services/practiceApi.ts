import type { PracticeTurnInput, SessionSummary, SubmitPracticeTurnResult, UploadDraft } from "../types/app";

import * as sessionApi from "./sessionApi";

export async function createPracticeSession(draft: UploadDraft): Promise<{ sessionId: string }> {
  if (draft.source === "file") {
    const mediaId = draft.uploadedMedia?.mediaId;
    if (!mediaId) {
      throw {
        code: "SESSION_START_FAILED",
        message: "图片上传结果缺失，请返回首页重新选择。",
      };
    }
    return sessionApi.createPracticeSession(mediaId);
  }

  const sampleSceneId = draft.sampleSceneId;
  if (!sampleSceneId) {
    throw {
      code: "SESSION_START_FAILED",
      message: "示例场景缺失，请返回首页重新选择。",
    };
  }
  return sessionApi.createSamplePracticeSession(sampleSceneId);
}

export async function getPracticeSession(sessionId: string): Promise<SessionSummary> {
  return sessionApi.getPracticeSession(sessionId);
}

export async function submitPracticeTurn(
  sessionId: string,
  input: PracticeTurnInput,
): Promise<SubmitPracticeTurnResult> {
  return sessionApi.submitPracticeTurn(sessionId, input);
}
