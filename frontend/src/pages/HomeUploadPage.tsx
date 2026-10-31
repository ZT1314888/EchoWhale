import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, Check, Mic, Play, Sparkles, Star } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { HomeComposer } from "../components/HomeComposer";
import { EmptyState, Eyebrow, SectionTitle } from "../components/ui";
import { sampleScenes } from "../data/sampleScenes";
import { listHistorySessions } from "../services/historyApi";
import type { HistoryEntry } from "../types/app";

const LOGIN_SUCCESS_TOAST_MS = 2500;

// 场景条是静态产品文案（EchoWhale 真实覆盖的三类生活场景），不是数据。
const MARQUEE = ["Coffee shop 咖啡店", "Office 办公室", "Asking directions 问路"];

// 没有数据源、也不是产品事实的指标一律不编造，这里只列真实存在的约束。
// 原型 hero 的 4.9 星 / 12,400+ 学员 / 头像堆 是编造的用户量与社会证明，已整块删除。
const TRUST_STATS = [
  { value: "A1-C2", label: "levels 全等级" },
  { value: "10 MB", label: "JPG / PNG / WebP" },
  { value: "3", label: "sample scenes 示例场景" },
];

function formatDate(value: string): string {
  return value.slice(0, 10);
}

export function HomeUploadPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const [selectedSceneId, setSelectedSceneId] = useState(sampleScenes[0].id);
  const [fileName, setFileName] = useState("");
  const [recent, setRecent] = useState<HistoryEntry[] | null>(null);
  const [showLoginSuccess, setShowLoginSuccess] = useState(
    Boolean((location.state as { loginSuccess?: boolean } | null)?.loginSuccess),
  );

  useEffect(() => {
    const routeState = location.state as { loginSuccess?: boolean } | null;
    if (!routeState?.loginSuccess) {
      return;
    }

    // 提示的展示值已在 useState 初始化时从 route state 读取（登录页必然跨路由
    // 跳回首页，本组件必经重新挂载，初始化器总会执行）。effect 只负责用 replace
    // 清掉 route state，防止刷新后 loginSuccess 残留导致提示复现——清路由是
    // 对外部系统（router）的合法 effect 副作用。
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

  useEffect(() => {
    if (!showLoginSuccess) {
      return;
    }

    const timerId = window.setTimeout(() => {
      setShowLoginSuccess(false);
    }, LOGIN_SUCCESS_TOAST_MS);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [showLoginSuccess]);

  // 「继续学习」只在登录态有意义（匿名请求必然 401），失败静默降级为不显示。
  useEffect(() => {
    if (auth.status !== "authenticated") {
      return;
    }

    let alive = true;
    listHistorySessions({ limit: 3 })
      .then((page) => {
        if (alive) {
          setRecent(page.items);
        }
      })
      .catch(() => {
        if (alive) {
          setRecent(null);
        }
      });

    return () => {
      alive = false;
    };
  }, [auth.status]);

  // 登出后不重新请求也不该继续显示上一个账号的历史，直接按当前登录态派生。
  const visibleRecent = auth.status === "authenticated" ? recent : null;

  function startFromSample(sampleSceneId: string) {
    setSelectedSceneId(sampleSceneId);
    navigate("/session/loading", {
      state: { draft: { source: "sample", sampleSceneId } },
    });
  }

  function startFromFile(file: File) {
    setFileName(file.name);
    navigate("/session/loading", {
      state: { draft: { source: "file", fileName: file.name, file } },
    });
  }

  return (
    <div>
      {/* ============ HERO ============ */}
      <section className="relative overflow-hidden">
        <div className="grid-pattern pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_75%_65%_at_50%_0%,black,transparent)]" />
        <div className="pointer-events-none absolute -top-40 left-1/2 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-r from-[#4f46e5]/15 via-[#a78bfa]/15 to-[#d8f34e]/20 blur-[100px]" />

        <div className="relative mx-auto max-w-7xl px-4 pb-10 pt-12 sm:px-6 sm:pt-16">
          <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="stagger">
              <Eyebrow>Scene to conversation · 从场景到开口</Eyebrow>
              <h1 className="font-display mt-6 text-[40px] font-bold leading-[1.02] tracking-tight sm:text-[56px] lg:text-[64px]">
                <span className="sr-only">上传一个场景，马上开口练习</span>
                <span aria-hidden="true">
                  上传一个场景，
                  <br />
                  <span className="font-serif-accent font-medium text-gradient-dark">马上开口练习。</span>
                </span>
              </h1>
              <p className="mt-4 text-[17px] font-medium tracking-tight text-stone-500">
                一张生活照片 · 一个真实角色 · 一轮安静的口语练习
              </p>
              <p className="mt-4 max-w-md text-[14.5px] leading-relaxed text-stone-500">
                Upload one everyday photo, and EchoWhale reads the scene, picks the role, and
                prepares your first line. 上传一张生活图片，EchoWhale 会读出场景、定好角色，再准备第一句开场提示。
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <a
                  href="#start"
                  className="group flex items-center gap-2 rounded-full bg-[#131311] px-7 py-4 text-[14px] font-bold text-white shadow-[0_20px_40px_-16px_rgba(19,19,17,0.5)] transition hover:bg-black"
                >
                  <Mic size={16} className="text-[#d8f34e]" aria-hidden="true" />
                  Start speaking
                  <span aria-hidden="true" className="font-normal text-white/50">开始练习</span>
                  <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" aria-hidden="true" />
                </a>
                <Link
                  to="/progress"
                  className="flex items-center gap-1.5 rounded-full border border-[#131311]/12 bg-white/70 px-6 py-4 text-[14px] font-bold transition hover:border-[#131311]/30 glass"
                >
                  My progress
                  <span aria-hidden="true" className="font-normal text-stone-400">进度</span>
                </Link>
              </div>

              <div className="mt-9 flex flex-wrap items-center gap-6 text-[12px]">
                {TRUST_STATS.map((stat) => (
                  <span key={stat.value}>
                    <b className="font-display text-[15px]">{stat.value}</b>
                    <br />
                    <span className="text-stone-500">{stat.label}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* 右栏是真实的最近一场练习；没有历史时显示空态，绝不放假对话。 */}
            <div className="relative hidden lg:block">
              <div className="pointer-events-none absolute -inset-8 rounded-[48px] bg-gradient-to-br from-[#4f46e5]/10 via-transparent to-[#d8f34e]/15 blur-2xl" />
              <div className="animate-float relative rounded-[28px] border border-[#131311]/8 bg-white/90 p-5 shadow-[0_40px_80px_-32px_rgba(19,19,17,0.3)] glass">
                <div className="flex items-center gap-3 border-b border-stone-100 pb-4">
                  <span className="relative grid h-11 w-11 place-items-center rounded-2xl bg-[#131311] text-[#d8f34e]">
                    <Sparkles size={20} aria-hidden="true" />
                    <span className="absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-emerald-500" />
                  </span>
                  <div className="flex-1">
                    <p className="text-[14px] font-bold">Your last session</p>
                    <p className="flex items-center gap-1.5 text-[11.5px] text-stone-500">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      {visibleRecent && visibleRecent.length > 0 ? "Recently practiced" : "No session yet"}
                    </p>
                  </div>
                </div>

                {visibleRecent && visibleRecent.length > 0 ? (
                  <div className="space-y-3 py-4">
                    <div className="rounded-2xl rounded-tl-md border border-stone-100 bg-stone-50 p-3.5">
                      <p className="text-[13.5px] font-bold leading-relaxed">{visibleRecent[0].sceneTitle}</p>
                      <p className="mt-1 text-[11.5px] text-stone-400">{visibleRecent[0].roleLabel}</p>
                    </div>
                    <div className="rounded-2xl bg-[#d8f34e]/25 p-3">
                      <p className="text-[12px] font-semibold leading-snug">{visibleRecent[0].reviewTitle}</p>
                      <p className="mt-0.5 text-[11.5px] text-stone-500">{visibleRecent[0].reviewSummary}</p>
                    </div>
                    <Link
                      to={`/session/${visibleRecent[0].id}/review`}
                      className="flex items-center justify-center gap-1.5 rounded-2xl border border-[#131311]/10 px-4 py-3 text-[12.5px] font-bold transition hover:bg-[#131311] hover:text-white"
                    >
                      查看这次复盘
                      <ArrowUpRight size={14} aria-hidden="true" />
                    </Link>
                  </div>
                ) : (
                  <div className="py-4">
                    <EmptyState
                      icon={<Mic size={22} aria-hidden="true" />}
                      title="还没有练习记录"
                      desc="上传一张生活场景图片，完成第一轮练习后这里会显示最近的一次复盘。"
                    />
                  </div>
                )}

                <div className="flex items-center gap-2.5 border-t border-stone-100 pt-4">
                  <div className="flex h-12 flex-1 items-center gap-[3px] rounded-full bg-stone-100 px-4">
                    {[0.5, 0.9, 0.6, 1, 0.4, 0.8, 0.55, 0.75, 0.45, 0.9].map((height, index) => (
                      <span
                        key={index}
                        className="wave-bar w-[3px] rounded-full bg-[#131311]"
                        style={{ height: `${height * 22}px`, animationDelay: `${index * 0.11}s` }}
                      />
                    ))}
                    <span className="ml-2 text-[11px] font-medium text-stone-400">Deepgram voice · 实时语音</span>
                  </div>
                  <span className="grid h-12 w-12 place-items-center rounded-full bg-[#131311] text-[#d8f34e]">
                    <Mic size={18} aria-hidden="true" />
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="relative border-y border-[#131311]/8 bg-[#131311] py-3.5 text-white">
          <div className="flex overflow-hidden">
            <div className="animate-marquee flex shrink-0 items-center gap-8 pr-8">
              {[...MARQUEE, ...MARQUEE, ...MARQUEE, ...MARQUEE].map((item, index) => (
                <span
                  key={index}
                  className="flex items-center gap-8 whitespace-nowrap text-[12.5px] font-bold uppercase tracking-[0.18em] text-white/70"
                >
                  {item} <Sparkles size={13} className="text-[#d8f34e]" aria-hidden="true" />
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ============ SETUP ============ */}
      <section id="start" className="mx-auto max-w-7xl scroll-mt-24 px-4 pt-16 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionTitle
            en="Start from a scene"
            cn="开始一轮练习"
            desc="Two entrances — pick a sample scene, or upload your own photo. 两种入口：示例场景，或上传自己的图片。"
          />
          <span className="rounded-full border border-[#131311]/10 bg-white/70 px-4 py-2 text-[12px] font-semibold text-stone-500">
            No. 01 — Setup · 配置
          </span>
        </div>

        <div className="mt-7 grid gap-5 lg:grid-cols-[1.5fr_1fr]">
          <HomeComposer
            selectedSceneId={selectedSceneId}
            onSelectScene={startFromSample}
            onSelectFile={startFromFile}
            fileName={fileName}
          />

          <div className="flex flex-col gap-5">
            <div className="noise relative overflow-hidden rounded-[28px] bg-[#131311] p-6 text-white shadow-[0_32px_64px_-24px_rgba(19,19,17,0.5)] sm:p-7">
              <div className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-[#4f46e5]/40 blur-[80px]" />
              <div className="relative">
                <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/45">How it works · 练习流程</p>
                <ol className="mt-3 space-y-2">
                  {[
                    { en: "Read the scene", cn: "读出场景", desc: "视觉识别图片里的地点与情境" },
                    { en: "Pick the role", cn: "定好角色", desc: "由后端下发这一轮你要对话的对方" },
                    { en: "Speak it out", cn: "开口回应", desc: "语音优先，文字随时可以补充" },
                    { en: "Review it", cn: "复盘一轮", desc: "逐字稿与四条反馈留档可回看" },
                  ].map((step, index) => (
                    <li
                      key={step.en}
                      className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3"
                    >
                      <span className="font-display grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-[#d8f34e] text-[13px] font-bold text-[#131311]">
                        {index + 1}
                      </span>
                      <span className="flex-1">
                        <span className="block text-[13.5px] font-bold">
                          {step.en}
                          <span aria-hidden="true" className="ml-1 text-[11px] font-normal text-white/45">
                            · {step.cn}
                          </span>
                        </span>
                        <span className="block text-[11.5px] text-white/45">{step.desc}</span>
                      </span>
                    </li>
                  ))}
                </ol>
                <Link
                  to="/history"
                  className="group mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-[#d8f34e] px-6 py-4 text-[14.5px] font-bold text-[#131311] transition hover:bg-[#e5ff70]"
                >
                  Open my library
                  <span aria-hidden="true" className="font-normal opacity-60">练习历史</span>
                  <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" aria-hidden="true" />
                </Link>
              </div>
            </div>

            {visibleRecent && visibleRecent.length > 0 ? (
              <div className="rounded-[28px] border border-[#131311]/8 bg-white p-5">
                <div className="flex items-center justify-between">
                  <p className="text-[13px] font-bold">
                    Continue
                    <span aria-hidden="true" className="font-normal text-stone-400">继续学习</span>
                  </p>
                  <Link to="/history" className="flex items-center gap-0.5 text-[12px] font-bold text-[#4f46e5] hover:underline">
                    All <ArrowUpRight size={13} aria-hidden="true" />
                  </Link>
                </div>
                <div className="mt-3 space-y-2">
                  {visibleRecent.map((item) => (
                    <Link
                      key={item.id}
                      to={`/session/${item.id}/review`}
                      className="group flex items-center gap-3 rounded-2xl bg-stone-50 p-3 transition hover:bg-[#131311] hover:text-white"
                    >
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-emerald-500/15 text-emerald-600 group-hover:bg-white/10 group-hover:text-emerald-300">
                        <Play size={15} className="ml-0.5" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-bold">{item.sceneTitle}</span>
                        <span className="block text-[11.5px] opacity-50">
                          {item.roleLabel} · {formatDate(item.practicedAt)}
                        </span>
                      </span>
                      <Check size={15} className="shrink-0 opacity-40" aria-hidden="true" />
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {/* ============ CLOSING ============ */}
      <section className="mx-auto max-w-7xl px-4 pb-4 pt-20 sm:px-6">
        <div className="noise relative overflow-hidden rounded-[32px] bg-[#131311] px-7 py-9 text-white sm:flex sm:items-end sm:justify-between sm:px-10 sm:py-11">
          <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-[#4f46e5]/30 blur-[100px]" />
          <div className="relative">
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-[#d8f34e]">One conversation at a time</p>
            <h2 className="font-display mt-3 text-[30px] font-bold leading-tight tracking-tight sm:text-[38px]">
              A little braver,
              <span className="font-serif-accent ml-2 font-medium text-white/60">every day.</span>
            </h2>
            <p className="mt-2 text-[13px] text-white/50">
              每天开口一点点，自信就多一点。 A few minutes can change how you sound.
            </p>
          </div>
          <a
            href="#start"
            className="group relative mt-6 inline-flex shrink-0 items-center gap-2 rounded-full bg-[#d8f34e] px-6 py-3.5 text-[13px] font-bold text-[#131311] transition hover:bg-white sm:mt-0"
          >
            Start a conversation
            <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </a>
        </div>
      </section>

      {showLoginSuccess ? (
        <section
          role="status"
          aria-live="polite"
          className="fixed bottom-6 left-1/2 z-50 flex w-[min(92vw,26rem)] -translate-x-1/2 items-center gap-4 rounded-2xl border border-[#131311]/10 bg-white p-4 shadow-[0_24px_48px_-24px_rgba(19,19,17,0.4)]"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#d8f34e] text-[#131311]">
            <Star size={18} aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] font-bold uppercase tracking-[0.16em] text-[#4f46e5]">登录成功</span>
            <span className="block text-[13px] font-semibold text-stone-600">已成功登录，欢迎回来。</span>
          </span>
          <button
            type="button"
            aria-label="关闭登录成功提示"
            onClick={() => setShowLoginSuccess(false)}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-[#131311]"
          >
            关闭提示
          </button>
        </section>
      ) : null}
    </div>
  );
}
