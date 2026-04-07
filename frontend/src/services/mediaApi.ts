import type { AppError, UploadedMedia } from "../types/app";
import { apiFetch } from "./apiClient";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
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
