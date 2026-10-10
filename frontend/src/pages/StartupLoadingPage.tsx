import { Check, Ear, FileUp, Lightbulb, Sparkles, Target, Terminal, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { StartupAnalysisOrb } from "../components/StartupAnalysisOrb";
import { uploadMedia } from "../services/mediaApi";
import { createPracticeSession } from "../services/practiceApi";
import type { AppError, SceneAnalysisStatusValue, UploadDraft, UploadedMedia } from "../types/app";

type LoadingState = {
  draft?: UploadDraft;
};

// 三个阶段与后端真实存在的产物一一对应（场景 / 角色 / 可进入练习）。
// 原型的第四步 "Composing"（谱写计划）在后端没有对应产物，不渲染。
const ANALYSIS_STAGES = [
  { key: "scene", icon: Ear, en: "Reading the scene", cn: "读场景", desc: "识别图片里的地点与情境" },
  { key: "role", icon: Target, en: "Casting the role", cn: "定角色", desc: "确定这一轮对话的对方" },
  { key: "ready", icon: Sparkles, en: "Preparing your opener", cn: "准备开场", desc: "生成第一句可以直接接话的提示" },
] as const;

// 异步分析进行中把假进度锁在"角色"档，等轮询真实 ready 再放行。
const ANALYSIS_HOLD_STAGE = 1;

const WAIT_TIPS = [
  "先说完整句子，比追求完美更容易被听懂。",
  "连接词值得刻意练习：because / however / for example。",
  "流利优先于准确，卡住时用一句简单句把意思说圆。",
];

/** 深色舞台上的动作按钮：primary 是 lime 实心，ghost 是描边。 */
function LoadingAction({
  label,
  onClick,
  variant = "primary",
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  variant?: "primary" | "ghost";
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        variant === "primary"
          ? "rounded-full bg-[#d8f34e] px-7 py-3.5 text-[14px] font-bold text-[#131311] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
          : "rounded-full border border-white/20 px-6 py-3.5 text-[13.5px] font-bold text-white/80 transition hover:bg-white/10"
      }
    >
      {label}
    </button>
  );
}

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
  const [latestAnalysisStatus, setLatestAnalysisStatus] = useState<SceneAnalysisStatusValue | null>(null);
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

  // 进度环只反映真实阶段：没有上传/分析的真实进度就不编造百分比。
  const progress = useMemo(() => {
    if (uploadError || sessionError) {
      return 0;
    }
    return ((displayStage + 1) / ANALYSIS_STAGES.length) * 100;
  }, [displayStage, uploadError, sessionError]);

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

  const returnHome = useCallback(() => {
    navigate("/");
  }, [navigate]);

  function cancelAnalysisWait() {
    analysisAbortRef.current?.abort();
    navigate("/");
  }

  const primaryLabel = startingSession
    ? analysisPending
      ? "正在分析场景…"
      : "正在创建练习…"
    : "进入练习";

  // 真实可得的日志：文件名与上传状态、场景分析的实时状态、会话创建结果。
  // 原型的 material.received / 128 sentences / distilling phrases / tuning goals
  // 都没有后端来源，已删除。
  const logLines = [
    {
      key: "upload",
      text: draft?.source === "file" ? `upload.media — ${draft.fileName ?? "image"}` : "draft.sample — 示例场景",
    },
    { key: "scene", text: `scene.analysis — ${latestAnalysisStatus ?? (analysisPending ? "pending" : "queued")}` },
  ];

  return (
    <div className="noise relative overflow-hidden bg-[#131311] text-white">
      <div className="grid-pattern-light pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute left-1/2 top-0 h-[420px] w-[720px] -translate-x-1/2 rounded-full bg-[#4f46e5]/25 blur-[130px]" />
      <div className="pointer-events-none absolute -left-24 bottom-0 h-72 w-72 rounded-full bg-[#d8f34e]/10 blur-[110px]" />

      <div className="relative mx-auto max-w-5xl px-4 py-14 sm:px-6">
        <main aria-label="上传分析中">
          <div className="text-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.2em] text-white/70">
              <span className={`h-2 w-2 rounded-full bg-[#d8f34e] ${isComplete ? "" : "animate-blink"}`} />
              {isComplete ? "Scene ready · 场景已就绪" : "Reading your scene · 正在读场景"}
            </span>
            <h1 className="font-display mx-auto mt-6 max-w-2xl text-[34px] font-bold leading-[1.05] tracking-tight sm:text-[46px]">
              {isComplete ? (
                <>
                  Your scene is{" "}
                  <span className="font-serif-accent font-medium text-gradient">ready.</span>
                </>
              ) : (
                <>
                  正在分析你的上传内容
                  <span className="font-serif-accent font-medium text-white/60">…</span>
                </>
              )}
            </h1>
            <p className="mx-auto mt-3 max-w-md text-[13.5px] leading-relaxed text-white/50">
              {draft?.fileName
                ? `我们正在识别 ${draft.fileName} 的环境线索、分配角色，并准备第一轮可直接接话的开场。`
                : "我们正在识别环境、分配角色，并准备第一轮可直接接话的开场。"}
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-[12px] font-semibold">
              {draft?.fileName ? (
                <span className="rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5 text-white/75">
                  {draft.fileName}
                </span>
              ) : null}
              {uploadedMedia ? (
                <span className="rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5 text-white/75">
                  {uploadedMedia.contentType}
                </span>
              ) : null}
              {analysisPending ? (
                <span className="rounded-full bg-[#d8f34e] px-3.5 py-1.5 font-bold text-[#131311]">
                  场景分析排队中
                </span>
              ) : null}
            </div>
            {/* 后端返回的原始错误文案逐字展示：这是用户唯一能据此判断下一步的线索。 */}
            {uploadError ? <p className="mt-4 text-[13px] text-rose-300">{uploadError}</p> : null}
            {sessionError ? <p className="mt-4 text-[13px] text-rose-300">{sessionError.message}</p> : null}
          </div>

          <div className="mt-10 rounded-[32px] border border-white/10 bg-white/[0.04] p-8 backdrop-blur sm:p-10">
            <div className="flex flex-col items-center gap-8 lg:flex-row lg:gap-12">
              <div className="relative shrink-0">
                <StartupAnalysisOrb stage={currentStage} isComplete={isComplete} />
                <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                  <div>
                    <p className="font-display text-[44px] font-bold leading-none">
                      {Math.round(progress)}
                      <span className="text-[18px] text-white/40">%</span>
                    </p>
                    <p className="mt-1.5 text-[11px] font-bold uppercase tracking-[0.2em] text-white/45">
                      {isComplete ? "Complete" : ANALYSIS_STAGES[displayStage].en}
                    </p>
                  </div>
                </div>
              </div>

              <div className="w-full flex-1">
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {ANALYSIS_STAGES.map((item, index) => {
                    const passed = index < displayStage || isComplete;
                    const active = index === displayStage && !isComplete;
                    return (
                      <div
                        key={item.key}
                        className={`flex items-center gap-3.5 rounded-2xl border p-4 transition-all duration-300 ${
                          passed
                            ? "border-[#d8f34e]/30 bg-[#d8f34e]/8"
                            : active
                              ? "border-white/25 bg-white/[0.07]"
                              : "border-white/8 bg-white/[0.02] opacity-50"
                        }`}
                      >
                        <span
                          className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                            passed ? "bg-[#d8f34e] text-[#131311]" : active ? "bg-white text-[#131311]" : "bg-white/10 text-white/50"
                          }`}
                        >
                          {passed ? <Check size={19} strokeWidth={3} aria-hidden="true" /> : <item.icon size={19} aria-hidden="true" />}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[13.5px] font-bold">
                            {item.en}
                            <span aria-hidden="true" className="text-[11.5px] font-normal text-white/45">
                              {" "}
                              {item.cn}
                            </span>
                          </span>
                          <span className="block truncate text-[11.5px] text-white/40">{item.desc}</span>
                        </span>
                        {active ? <span className="ml-auto h-2 w-2 shrink-0 animate-pulse rounded-full bg-[#d8f34e]" /> : null}
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 h-[6px] overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-[#d8f34e] transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {uploadError ? (
                <LoadingAction label="重试上传" onClick={retryUpload} />
              ) : sessionError?.code === "UNSUPPORTED_SCENE_IMAGE" ? (
                <LoadingAction label="返回首页重新选择" onClick={returnHome} />
              ) : sessionError?.code === "SCENE_ANALYSIS_FAILED" || sessionError?.code === "SCENE_ANALYSIS_TIMEOUT" ? (
                <>
                  <LoadingAction label="重试创建练习" onClick={() => void enterPractice()} />
                  <LoadingAction label="换一张图片" variant="ghost" onClick={returnHome} />
                </>
              ) : sessionError ? (
                <LoadingAction label="重试创建练习" onClick={() => void enterPractice()} />
              ) : (
                <>
                  <LoadingAction
                    label={primaryLabel}
                    disabled={!readyToEnter}
                    onClick={() => void enterPractice()}
                  />
                  {analysisPending ? (
                    <LoadingAction label="取消等待" variant="ghost" onClick={cancelAnalysisWait} />
                  ) : null}
                </>
              )}
            </div>
          </div>

          <div className="mt-5 grid gap-5 md:grid-cols-2">
            <div className="rounded-[28px] border border-white/10 bg-black/40 p-6">
              <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-white/40">
                <Terminal size={14} aria-hidden="true" /> Live log · 实时日志
              </p>
              <div role="log" aria-live="polite" className="mt-4 space-y-2.5 font-mono text-[12.5px]">
                {logLines.map((line) => (
                  <p key={line.key} className="text-white/70">
                    <span className="text-[#d8f34e]">✓</span> {line.text}
                  </p>
                ))}
                {isComplete ? (
                  <p className="text-[#d8f34e]">
                    <span>✓</span> session.ready — 可以进入练习了
                  </p>
                ) : (
                  <p className="animate-blink text-white/30">▊ processing…</p>
                )}
              </div>
            </div>

            <div className="rounded-[28px] bg-[#d8f34e] p-6 text-[#131311]">
              <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] opacity-60">
                <Lightbulb size={14} aria-hidden="true" /> While you wait · 等待锦囊
              </p>
              <ul className="mt-4 space-y-2.5 text-[13px] font-medium leading-relaxed">
                {WAIT_TIPS.map((tip, index) => (
                  <li key={tip} className="flex gap-2">
                    <span className="font-bold">{String(index + 1).padStart(2, "0")}.</span> {tip}
                  </li>
                ))}
              </ul>
              <p className="mt-4 flex items-center gap-2 text-[11.5px] font-semibold opacity-70">
                <FileUp size={13} aria-hidden="true" />
                {draft?.source === "file" ? "已选择图片" : "示例场景"}
                {uploadError || sessionError ? (
                  <span className="flex items-center gap-1 text-rose-700">
                    <X size={13} aria-hidden="true" /> 需要处理一下
                  </span>
                ) : null}
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
