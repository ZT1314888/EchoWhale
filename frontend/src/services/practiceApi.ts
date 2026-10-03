import type {
  SceneAnalysisStatusValue,
  SessionSummary,
  UploadDraft,
} from "../types/app";

import { waitForSceneAnalysis } from "./mediaApi";
import * as sessionApi from "./sessionApi";

const MAX_START_ATTEMPTS_AFTER_PENDING = 3;

const SAMPLE_SCENE_IDS = ["coffee", "office", "street"] as const;

type SampleSceneId = (typeof SAMPLE_SCENE_IDS)[number];

function isSampleSceneId(value: string | undefined): value is SampleSceneId {
  return typeof value === "string" && (SAMPLE_SCENE_IDS as readonly string[]).includes(value);
}

export async function createPracticeSession(
  draft: UploadDraft,
  options: {
    onAnalysisPending?: () => void;
    onAnalysisStatus?: (status: SceneAnalysisStatusValue) => void;
    signal?: AbortSignal;
  } = {},
): Promise<{ sessionId: string }> {
  let outcome = await startPracticeSession(draft, options.signal);

  if (outcome.kind === "analyzing") {
    options.onAnalysisPending?.();
    let pendingMediaId = outcome.mediaId;
    for (let attempt = 0; attempt < MAX_START_ATTEMPTS_AFTER_PENDING; attempt += 1) {
      await waitForSceneAnalysis(pendingMediaId, {
        signal: options.signal,
        onStatus: options.onAnalysisStatus,
      });
      outcome = await startPracticeSession(draft, options.signal);
      if (outcome.kind === "created") {
        return { sessionId: outcome.sessionId };
      }
      pendingMediaId = outcome.mediaId;
    }
    throw {
      code: "SCENE_ANALYSIS_TIMEOUT",
      message: "场景分析仍未就绪，请稍后重试或换一张图片。",
    };
  }

  return { sessionId: outcome.sessionId };
}

async function startPracticeSession(
  draft: UploadDraft,
  signal?: AbortSignal,
): Promise<sessionApi.SessionStartOutcome> {
  if (draft.source === "file") {
    const mediaId = draft.uploadedMedia?.mediaId;
    if (!mediaId) {
      throw {
        code: "SESSION_START_FAILED",
        message: "图片上传结果缺失，请返回首页重新选择。",
      };
    }
    return sessionApi.createPracticeSession(mediaId, signal);
  }

  const sampleSceneId = draft.sampleSceneId;
  if (!isSampleSceneId(sampleSceneId)) {
    throw {
      code: "SESSION_START_FAILED",
      message: "示例场景缺失，请返回首页重新选择。",
    };
  }
  return sessionApi.createSamplePracticeSession(sampleSceneId, signal);
}

export async function getPracticeSession(sessionId: string): Promise<SessionSummary> {
  return sessionApi.getPracticeSession(sessionId);
}
