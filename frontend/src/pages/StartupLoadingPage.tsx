import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { StartupAnalysisOrb } from "../components/StartupAnalysisOrb";
import { uploadMedia } from "../services/mediaApi";
import { createPracticeSession } from "../services/practiceApi";
import type {
  AppError,
  SceneAnalysisStatusValue,
  UploadDraft,
  UploadedMedia,
} from "../types/app";

type LoadingState = {
  draft?: UploadDraft;
};

const ANALYSIS_STAGES = [
  { key: "scene", label: "场景" },
  { key: "role", label: "角色" },
  { key: "ready", label: "准备完成" },
] as const;

// 异步分析进行中把假进度锁在"角色"档，等轮询真实 ready 再放行。
const ANALYSIS_HOLD_STAGE = 1;

export function StartupLoadingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const draft = (location.state as LoadingState | null)?.draft;
  const [stageIndex, setStageIndex] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [sessionError, setSessionError] = useState<AppError | null>(null);
  const [startingSession, setStartingSession] = useState(false);
  const [uploading, setUploading] = useState(draft?.source === "file");
  const [uploadedMedia, setUploadedMedia] = useState<UploadedMedia | undefined>(draft?.uploadedMedia);
  const [retryKey, setRetryKey] = useState(0);
  const [analysisPending, setAnalysisPending] = useState(false);
  const [latestAnalysisStatus, setLatestAnalysisStatus] = useState<SceneAnalysisStatusValue | null>(
    null,
  );
  const analysisAbortRef = useRef<AbortController | null>(null);

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
    return () => {
      // 离开页面时中止仍在进行的分析等待轮询。
      analysisAbortRef.current?.abort();
    };
  }, []);

  // 该 effect 是"路由 state（外部系统）→ 上传流程编排"的正当 effect 用法：
  // draft 变化时同步落 uploading/error 初值并启动异步上传。同步 setState 是
  // 请求生命周期的镜像（异步回调里才置位会出现"既不在上传也无错误"的空窗态），
  // 因此整块豁免 set-state-in-effect；draft 重来（retryKey）也依赖这里的同步重置。
  /* eslint-disable react-hooks/set-state-in-effect -- 外部系统同步 + 上传编排，见上 */
  useEffect(() => {
    if (draft?.source !== "file") {
      setUploading(false);
      return;
    }

    if (draft.uploadedMedia) {
      setUploadedMedia(draft.uploadedMedia);
      setUploading(false);
      setUploadError("");
      setSessionError(null);
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
    setSessionError(null);

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
  /* eslint-enable react-hooks/set-state-in-effect */

  const holdingForAnalysis = analysisPending && latestAnalysisStatus !== "ready";
  const displayStage = holdingForAnalysis ? Math.min(stageIndex, ANALYSIS_HOLD_STAGE) : stageIndex;
  const isComplete = displayStage === ANALYSIS_STAGES.length - 1;
  const currentStage = ANALYSIS_STAGES[displayStage].key;
  const readyToEnter = isComplete && !uploading && !uploadError && !startingSession;
  const nextDraft =
    draft?.source === "file" ? { ...draft, uploadedMedia } : (draft ?? { source: "sample", sampleSceneId: "coffee" });

  async function enterPractice() {
    if (!readyToEnter) {
      return;
    }

    const controller = new AbortController();
    analysisAbortRef.current = controller;
    setStartingSession(true);
    setAnalysisPending(false);
    setLatestAnalysisStatus(null);
    setSessionError(null);
    try {
      const created = await createPracticeSession(nextDraft, {
        onAnalysisPending: () => setAnalysisPending(true),
        onAnalysisStatus: (status) => setLatestAnalysisStatus(status),
        signal: controller.signal,
      });
      navigate(`/session/${created.sessionId}`, {
        state: { draft: nextDraft },
      });
    } catch (reason) {
      if ((reason as { name?: string } | null)?.name === "AbortError") {
        navigate("/");
        return;
      }
      const error = (reason as AppError | null) ?? {
        code: "SESSION_START_FAILED",
        message: "创建练习会话失败，请稍后重试。",
      };
      setSessionError(error);
      setAnalysisPending(false);
    } finally {
      setStartingSession(false);
    }
  }

  function retryUpload() {
    setRetryKey((current) => current + 1);
  }

  function returnHome() {
    navigate("/");
  }

  function cancelAnalysisWait() {
    analysisAbortRef.current?.abort();
    navigate("/");
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
            {sessionError ? <p className="muted-text loading-copy">{sessionError.message}</p> : null}
            {analysisPending && !sessionError ? (
              <p className="muted-text loading-copy">场景分析排队中，完成后会自动进入练习…</p>
            ) : null}

            <div className="loading-progress" aria-label="分析进度">
              {ANALYSIS_STAGES.map((item, index) => {
                const isActive = index === displayStage;
                const isDone = index < displayStage || isComplete;

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
            ) : sessionError?.code === "UNSUPPORTED_SCENE_IMAGE" ? (
              <div className="action-row">
                <button className="primary-button loading-cta" type="button" onClick={returnHome}>
                  返回首页重新选择
                </button>
              </div>
            ) : sessionError?.code === "SCENE_ANALYSIS_FAILED" || sessionError?.code === "SCENE_ANALYSIS_TIMEOUT" ? (
              <div className="action-row">
                <button className="primary-button loading-cta" type="button" onClick={enterPractice}>
                  重试创建练习
                </button>
                <button className="ghost-button loading-cta" type="button" onClick={returnHome}>
                  换一张图片
                </button>
              </div>
            ) : sessionError ? (
              <div className="action-row">
                <button className="primary-button loading-cta" type="button" onClick={enterPractice}>
                  重试创建练习
                </button>
              </div>
            ) : (
              <div className="action-row">
                <button
                  className="primary-button loading-cta"
                  type="button"
                  onClick={enterPractice}
                  disabled={!readyToEnter}
                >
                  {startingSession
                    ? analysisPending
                      ? "正在分析场景…"
                      : "正在创建练习…"
                    : "进入练习"}
                </button>
                {analysisPending ? (
                  <button
                    className="ghost-button loading-cta"
                    type="button"
                    onClick={cancelAnalysisWait}
                  >
                    取消等待
                  </button>
                ) : null}
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
