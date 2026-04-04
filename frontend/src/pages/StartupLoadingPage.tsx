import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { StartupAnalysisOrb } from "../components/StartupAnalysisOrb";
import { uploadMedia } from "../services/mediaApi";
import { createPracticeSession } from "../services/practiceApi";
import type { UploadDraft, UploadedMedia } from "../types/app";

type LoadingState = {
  draft?: UploadDraft;
};

const ANALYSIS_STAGES = [
  { key: "scene", label: "场景" },
  { key: "role", label: "角色" },
  { key: "ready", label: "准备完成" },
] as const;

export function StartupLoadingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const draft = (location.state as LoadingState | null)?.draft;
  const [stageIndex, setStageIndex] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(draft?.source === "file");
  const [uploadedMedia, setUploadedMedia] = useState<UploadedMedia | undefined>(draft?.uploadedMedia);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const timers = ANALYSIS_STAGES.slice(1).map((_, index) =>
      window.setTimeout(() => {
        setStageIndex(index + 1);
      }, (index + 1) * 1100),
    );

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  useEffect(() => {
    if (draft?.source !== "file") {
      setUploading(false);
      return;
    }

    if (draft.uploadedMedia) {
      setUploadedMedia(draft.uploadedMedia);
      setUploading(false);
      setUploadError("");
      return;
    }

    if (!draft.file) {
      setUploadError("上传文件已失效，请返回首页重新选择。");
      setUploading(false);
      return;
    }

    let active = true;
    setUploading(true);
    setUploadError("");

    uploadMedia(draft.file)
      .then((media) => {
        if (!active) {
          return;
        }
        setUploadedMedia(media);
        setUploading(false);
      })
      .catch((reason: { message?: string }) => {
        if (!active) {
          return;
        }
        setUploading(false);
        setUploadError(reason.message ?? "上传失败，请稍后重试。");
      });

    return () => {
      active = false;
    };
  }, [draft, retryKey]);

  const isComplete = stageIndex === ANALYSIS_STAGES.length - 1;
  const currentStage = ANALYSIS_STAGES[stageIndex].key;
  const readyToEnter = isComplete && !uploading && !uploadError;
  const nextDraft =
    draft?.source === "file" ? { ...draft, uploadedMedia } : (draft ?? { source: "sample", sampleSceneId: "coffee" });

  async function enterPractice() {
    if (!readyToEnter) {
      return;
    }

    const created = await createPracticeSession(nextDraft);
    navigate(`/session/${created.sessionId}`, {
      state: { draft: nextDraft },
    });
  }

  function retryUpload() {
    setRetryKey((current) => current + 1);
  }

  return (
    <div className="page-shell page-shell--loading">
      <div className="page-frame page-frame--loading">
        <main className="loading-stage" aria-label="上传分析中">
          <StartupAnalysisOrb stage={currentStage} isComplete={isComplete} />

          <section className="loading-card loading-card--immersive">
            <p className="eyebrow eyebrow--brand">ECHOWHALE 正在聆听这个场景</p>
            <h1>正在分析你的上传内容…</h1>
            <p className="muted-text loading-copy">
              {draft?.fileName
                ? `我们正在识别 ${draft.fileName} 的环境线索、分配角色，并准备第一轮可直接接话的开场。`
                : "我们正在识别环境、分配角色，并准备第一轮可直接接话的开场。"}
            </p>
            {draft?.source === "file" ? (
              <p className="muted-text loading-copy">
                {uploading
                  ? "图片正在上传到媒体存储…"
                  : uploadError
                    ? uploadError
                    : uploadedMedia
                      ? `图片已上传，可访问地址已生成：${uploadedMedia.filename}`
                      : "图片上传准备中…"}
              </p>
            ) : null}

            <div className="loading-progress" aria-label="分析进度">
              {ANALYSIS_STAGES.map((item, index) => {
                const isActive = index === stageIndex;
                const isDone = index < stageIndex || isComplete;

                return (
                  <span
                    key={item.key}
                    className={[
                      "info-pill",
                      isActive ? "info-pill--active" : "",
                      isDone ? "info-pill--complete" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {item.label}
                  </span>
                );
              })}
            </div>

            {uploadError ? (
              <div className="action-row">
                <button className="primary-button loading-cta" type="button" onClick={retryUpload}>
                  重试上传
                </button>
              </div>
            ) : (
              <button className="primary-button loading-cta" type="button" onClick={enterPractice} disabled={!readyToEnter}>
                进入练习
              </button>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}