import type { AppError, LearnerProfileOverview, ProfileErrorType, ProfileSceneCount } from "../types/app";
import { apiFetch } from "./apiClient";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

// 后端契约保持 snake_case，前端映射为 camelCase（与 historyApi 同一惯例）。
type BackendLearnerProfile = {
  cefr_estimate: string | null;
  error_types: { category: string; label: string; count: number }[];
  scenes: { scene_title: string; count: number }[];
  practiced_turn_count: number;
  updated_at: string | null;
};

function toError(message: string, code = "LEARNER_API_FAILED"): AppError {
  return { code, message };
}

function toErrorType(errorType: BackendLearnerProfile["error_types"][number]): ProfileErrorType {
  return {
    category: errorType.category,
    label: errorType.label,
    count: errorType.count,
  };
}

function toSceneCount(scene: BackendLearnerProfile["scenes"][number]): ProfileSceneCount {
  return {
    sceneTitle: scene.scene_title,
    count: scene.count,
  };
}

function toLearnerProfileOverview(payload: BackendLearnerProfile): LearnerProfileOverview {
  return {
    cefrEstimate: payload.cefr_estimate,
    errorTypes: payload.error_types.map(toErrorType),
    scenes: payload.scenes.map(toSceneCount),
    practicedTurnCount: payload.practiced_turn_count,
    updatedAt: payload.updated_at,
  };
}

export async function getLearnerProfile(): Promise<LearnerProfileOverview> {
  let response: Response;

  try {
    response = await apiFetch("/api/v1/learners/me/profile");
  } catch {
    throw toError("学习进度加载失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendLearnerProfile>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "学习进度加载失败。");
  }

  return toLearnerProfileOverview(payload.data);
}
