import type {
  AppError,
  SceneAnalysisStatus,
  SceneAnalysisStatusValue,
  UploadedMedia,
} from "../types/app";
import { apiFetch } from "./apiClient";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type SceneAnalysisStatusPayload = {
  media_id: string;
  status: string;
  prompt_version?: string | null;
  scene?: string | null;
  role?: string | null;
  confidence?: number | null;
  error_code?: number | null;
};


type MediaUploadResponse = {
  media_id: string;
  filename: string;
  content_type: string;
  file_size: number;
  storage_key: string;
  preview_url?: string | null;
  preview_url_expires_at?: string | null;
  upload_status: string;
};

function toError(message: string): AppError {
  return {
    code: "UPLOAD_FAILED",
    message,
  };
}

export async function uploadMedia(file: File): Promise<UploadedMedia> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;

  try {
    response = await apiFetch("/api/v1/media/upload", {
      method: "POST",
      body: formData,
    });
  } catch {
    throw toError("上传失败，请检查网络或稍后重试。");
  }

  const payload = (await response.json()) as ApiResponse<MediaUploadResponse>;

  if (!response.ok) {
    throw toError(payload.message ?? "上传失败，请稍后重试。");
  }

  const media = payload.data;

  return {
    mediaId: media?.media_id ?? "",
    filename: media?.filename ?? file.name,
    contentType: media?.content_type ?? file.type,
    fileSize: media?.file_size ?? file.size,
    storageKey: media?.storage_key ?? "",
    previewUrl: media?.preview_url ?? "",
    previewUrlExpiresAt: media?.preview_url_expires_at ?? "",
    uploadStatus: media?.upload_status ?? "uploaded",
  };
}

export async function getSceneAnalysisStatus(
  mediaId: string,
  options: { signal?: AbortSignal } = {},
): Promise<SceneAnalysisStatus> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/media/${mediaId}/scene-analysis`, {
      signal: options.signal,
    });
  } catch {
    throw toSceneError("查询场景分析状态失败，请稍后重试。");
  }

  const payload = (await response.json()) as ApiResponse<SceneAnalysisStatusPayload>;
  const data = payload.data;

  if (!response.ok || !data) {
    throw toSceneError(payload.message ?? "查询场景分析状态失败，请稍后重试。");
  }

  return {
    mediaId: data.media_id,
    status: data.status as SceneAnalysisStatusValue,
    promptVersion: data.prompt_version ?? undefined,
    scene: data.scene ?? undefined,
    role: data.role ?? undefined,
    confidence: data.confidence ?? undefined,
    errorCode: data.error_code ?? undefined,
  };
}

export const SCENE_ANALYSIS_POLL_INTERVAL_MS = 2000;
export const SCENE_ANALYSIS_POLL_TIMEOUT_MS = 60000;

const SCENE_ANALYSIS_UNSUPPORTED_CODE = 1007;

function toSceneError(message: string, code = "SCENE_ANALYSIS_STATUS_FAILED"): AppError {
  return { code, message };
}

function toAbortError(): Error {
  const error = new Error("场景分析等待已取消");
  error.name = "AbortError";
  return error;
}

function waitMilliseconds(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timerId = window.setTimeout(finish, ms);
    function finish() {
      window.clearTimeout(timerId);
      signal?.removeEventListener("abort", finish);
      resolve();
    }
    signal?.addEventListener("abort", finish, { once: true });
  });
}

export async function waitForSceneAnalysis(
  mediaId: string,
  options: {
    intervalMs?: number;
    timeoutMs?: number;
    signal?: AbortSignal;
    onStatus?: (status: SceneAnalysisStatusValue) => void;
  } = {},
): Promise<void> {
  const intervalMs = options.intervalMs ?? SCENE_ANALYSIS_POLL_INTERVAL_MS;
  const timeoutMs = options.timeoutMs ?? SCENE_ANALYSIS_POLL_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (options.signal?.aborted) {
      throw toAbortError();
    }
    await waitMilliseconds(intervalMs, options.signal);
    if (options.signal?.aborted) {
      throw toAbortError();
    }

    let snapshot: SceneAnalysisStatus;
    try {
      snapshot = await getSceneAnalysisStatus(mediaId, { signal: options.signal });
    } catch {
      if (options.signal?.aborted) {
        throw toAbortError();
      }
      // 单次轮询失败（网络抖动等）继续等待，由总超时兑底。
      continue;
    }

    options.onStatus?.(snapshot.status);

    if (snapshot.status === "ready") {
      return;
    }
    if (snapshot.status === "failed") {
      if (Number(snapshot.errorCode) === SCENE_ANALYSIS_UNSUPPORTED_CODE) {
        throw toSceneError(
          "图片暂不支持这类内容，请换一张生活场景更清晰的图片。",
          "UNSUPPORTED_SCENE_IMAGE",
        );
      }
      throw toSceneError("图片场景分析失败，请重试或换一张图片。", "SCENE_ANALYSIS_FAILED");
    }
  }

  throw toSceneError("场景分析等待超时，请稍后重试或换一张图片。", "SCENE_ANALYSIS_TIMEOUT");
}
