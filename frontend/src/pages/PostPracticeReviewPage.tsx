import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  History,
  Mic,
  Plus,
  Sparkles,
  TrendingUp,
  Wrench,
} from "lucide-react";

import { SpeakButton } from "../components/SpeakButton";
import { EmptyState, ScoreBar, ScoreRing } from "../components/ui";
import { getHistorySessionMessages } from "../services/historyApi";
import { getPracticeReview as getRealPracticeReview } from "../services/reviewApi";
import type { PracticeMessage, ReviewSummary } from "../types/app";

const TRANSCRIPT_PAGE_SIZE = 20;

type Tab = "overview" | "transcript";

export function PostPracticeReviewPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [review, setReview] = useState<ReviewSummary | null>(null);
  const [hasError, setHasError] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [transcript, setTranscript] = useState<PracticeMessage[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let alive = true;
    getRealPracticeReview(sessionId)
      .then((value) => {
        if (alive) {
          setReview(value);
        }
      })
      .catch(() => {
        if (alive) {
          setHasError(true);
        }
      });

    return () => {
      alive = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!review) {
      return;
    }

    let alive = true;
    getHistorySessionMessages(sessionId, { limit: TRANSCRIPT_PAGE_SIZE })
      .then((page) => {
        if (!alive) {
          return;
        }
        setTranscript(page.items);
        setHasMore(page.page.hasMore);
        setNextCursor(page.page.nextCursor);
      })
      .catch(() => {
        // 逐字稿是复盘的补充材料，取不到时保持空态，不把整页打成错误页。
      });

    return () => {
      alive = false;
    };
  }, [review, sessionId]);

  async function loadMoreTranscript() {
    if (!hasMore || !nextCursor || loadingMore) {
      return;
    }
    setLoadingMore(true);
    try {
      const page = await getHistorySessionMessages(sessionId, {
        limit: TRANSCRIPT_PAGE_SIZE,
        cursor: nextCursor,
      });
      setTranscript((previous) => [...page.items, ...previous]);
      setHasMore(page.page.hasMore);
      setNextCursor(page.page.nextCursor);
    } catch {
      setHasMore(false);
    } finally {
      setLoadingMore(false);
    }
  }

  if (hasError && !review) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-20 text-center sm:px-6">
        <h1 className="font-display text-[26px] font-bold tracking-tight">练后反馈还没准备好</h1>
        <p className="mt-3 text-[13.5px] leading-relaxed text-stone-500">
          这一轮的复盘暂时读不到，可以回到练习页再练一轮。
        </p>
        <Link
          to={`/session/${sessionId}`}
          className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#131311] px-6 py-3 text-[13px] font-bold text-white"
        >
          <ArrowLeft size={15} aria-hidden="true" />
          返回练习
        </Link>
      </main>
    );
  }

  if (!review) {
    return (
      <main className="grid min-h-[70vh] place-items-center px-4">
        <div className="text-center">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">
            <Sparkles size={24} aria-hidden="true" />
          </span>
          <h1 className="font-display mt-4 text-lg font-bold">正在生成练后反馈…</h1>
        </div>
      </main>
    );
  }

  const feedback = review.feedback;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-center gap-4">
        <Link
          to="/history"
          aria-label="返回练习历史"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[#131311]/10 bg-white transition hover:bg-[#131311] hover:text-white"
        >
          <ArrowLeft size={18} aria-hidden="true" />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-stone-400">
            练后复盘 · {sessionId.slice(0, 6).toUpperCase()}
          </p>
          <h1 className="font-display mt-1 truncate text-[26px] font-bold tracking-tight sm:text-[32px]">
            {review.title}
          </h1>
        </div>
        <div className="flex gap-2">
          <Link
            to="/"
            className="flex items-center gap-1.5 rounded-full border border-[#131311]/12 bg-white px-5 py-3 text-[13px] font-bold transition hover:border-[#131311]"
          >
            <Plus size={15} aria-hidden="true" />
            换一个场景
          </Link>
          <button
            type="button"
            onClick={() => navigate(`/session/${sessionId}`)}
            className="flex items-center gap-1.5 rounded-full bg-[#131311] px-5 py-3 text-[13px] font-bold text-white transition hover:bg-black"
          >
            <Mic size={15} className="text-[#d8f34e]" aria-hidden="true" />
            再练一轮
          </button>
        </div>
      </div>

      {/* h2「练后反馈」保留给路由测试的 level-2 精确匹配；成绩带后端无数字，一律 0 / —。 */}
      <h2 className="sr-only">练后反馈</h2>

      <div className="noise relative mt-6 overflow-hidden rounded-[32px] bg-[#131311] text-white">
        <div className="grid-pattern-light pointer-events-none absolute inset-0" />
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[#4f46e5]/35 blur-[110px]" />
        <div className="relative grid items-center gap-8 p-8 sm:p-10 lg:grid-cols-[auto_1fr_auto]">
          <div className="flex items-center gap-6">
            <div className="rounded-[28px] border border-white/12 bg-white/[0.05] p-4">
              <ScoreRing score={0} size={148} stroke={12} dark label="—" />
            </div>
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#d8f34e]">
                Overall · 综合得分
              </p>
              <p className="font-display mt-2 text-[30px] font-bold leading-none">{review.title}</p>
              <p className="font-serif-accent mt-1 text-[17px] text-white/50">本轮回响</p>
              <p className="mt-3 max-w-xs text-[12.5px] leading-relaxed text-white/55">{review.highlight}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2.5 lg:grid-cols-1 lg:gap-3">
            {[
              ["—", "Takes 轮次"],
              ["—", "Words 词数"],
              ["—", "Duration 时长"],
            ].map(([value, label]) => (
              <div
                key={label}
                className="rounded-2xl border border-white/10 bg-white/[0.05] px-6 py-4 text-center lg:px-10"
              >
                <p className="font-display text-[24px] font-bold">{value}</p>
                <p className="mt-0.5 text-[11px] font-semibold uppercase tracking-widest text-white/40">{label}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="relative border-t border-white/10 px-8 py-3 text-[11.5px] text-white/40 sm:px-10">
          后端不提供分数、词数与时长，「综合得分 / 维度得分」在这批里保持空态。
        </p>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <div className="rounded-[28px] border border-[#131311]/8 bg-white p-6">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-stone-400">Dimensions · 维度得分</p>
          <div className="mt-4 space-y-4">
            {[
              ["Fluency", "流利度", 80],
              ["Pronunciation", "发音", 160],
              ["Grammar", "语法", 240],
              ["Vocabulary", "词汇", 320],
              ["Coherence", "连贯性", 400],
            ].map(([label, cn, delay]) => (
              <ScoreBar key={label as string} label={label as string} cn={cn as string} score={0} delay={delay as number} />
            ))}
          </div>
          <div className="mt-5 rounded-2xl bg-[#faf9f6] p-4">
            <p className="text-[12px] font-bold text-[#131311]">下一次尝试</p>
            <p className="mt-1 text-[13px] leading-relaxed text-stone-600">{review.nextTry}</p>
          </div>
        </div>

        <div className="rounded-[28px] border border-[#131311]/8 bg-[#faf9f6] p-6">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="复盘视图">
            {(
              [
                { id: "overview", icon: Sparkles, label: "导演笔记" },
                { id: "transcript", icon: History, label: "逐字稿" },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
                className={`flex items-center gap-1.5 rounded-full px-5 py-2.5 text-[13px] font-bold transition ${
                  tab === item.id ? "bg-[#131311] text-white shadow-lg" : "bg-white text-stone-500 hover:text-[#131311]"
                }`}
              >
                <item.icon size={14} aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </div>

          {tab === "overview" ? (
            <div className="mt-5 space-y-5">
              <section>
                <h3 className="flex items-center gap-2 text-[13px] font-bold">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-emerald-500/15 text-emerald-600">
                    <Check size={14} strokeWidth={3} aria-hidden="true" />
                  </span>
                  Highlights · 高光时刻
                </h3>
                <div className="mt-3 space-y-2">
                  <div className="rounded-2xl border border-emerald-600/10 bg-emerald-500/[0.06] p-4">
                    <p className="text-[12.5px] font-bold text-[#131311]">{feedback.grammar.title}</p>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-stone-600">{feedback.grammar.body}</p>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="flex items-center gap-2 text-[13px] font-bold">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-[#131311] text-[#d8f34e]">
                    <Wrench size={13} aria-hidden="true" />
                  </span>
                  Polish these · 打磨重点
                </h3>
                <div className="mt-3 space-y-2">
                  <div className="rounded-2xl bg-white p-4">
                    <p className="text-[12.5px] font-bold text-[#131311]">{feedback.moreNatural.title}</p>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-stone-600">{feedback.moreNatural.body}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4">
                    <p className="text-[12.5px] font-bold text-[#131311]">{feedback.nextStep.title}</p>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-stone-600">{feedback.nextStep.body}</p>
                  </div>
                </div>
              </section>

              <section className="rounded-2xl bg-[#131311] p-4 text-white">
                <h3 className="text-[13px] font-bold">
                  金句 · 点一下跟读
                </h3>
                <div className="mt-2.5 space-y-2">
                  {feedback.usefulWords.words.length ? (
                    feedback.usefulWords.words.map((word) => (
                      <div
                        key={word}
                        className="flex items-center gap-2.5 rounded-xl bg-white/10 p-3"
                      >
                        <SpeakButton text={word} compact />
                        <span className="text-[12.5px] font-bold">{word}</span>
                      </div>
                    ))
                  ) : (
                    <p className="rounded-xl bg-white/10 p-3 text-[12.5px] leading-relaxed text-white/60">
                      {feedback.usefulWords.body}
                    </p>
                  )}
                </div>
              </section>
            </div>
          ) : (
            <div className="mt-5 space-y-2.5">
              {hasMore ? (
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={() => {
                    void loadMoreTranscript();
                  }}
                  className="w-full rounded-full border border-[#131311]/12 bg-white px-4 py-2.5 text-[12.5px] font-bold transition hover:border-[#131311] disabled:opacity-50"
                >
                  {loadingMore ? "加载中..." : "加载更早消息"}
                </button>
              ) : null}
              {transcript.length ? (
                transcript.map((message) => (
                  <article
                    key={message.id}
                    className={`rounded-2xl p-4 ${
                      message.role === "learner" ? "ml-6 bg-[#131311] text-white sm:ml-12" : "mr-6 bg-white sm:mr-12"
                    }`}
                  >
                    <p
                      className={`flex items-center gap-2 text-[12px] font-bold ${
                        message.role === "learner" ? "text-[#d8f34e]" : "text-[#4f46e5]"
                      }`}
                    >
                      {message.label}
                    </p>
                    <p
                      className={`mt-1.5 text-[13.5px] leading-relaxed ${
                        message.role === "learner" ? "" : "text-stone-700"
                      }`}
                    >
                      {message.content}
                    </p>
                    {message.role === "coach" ? <SpeakButton text={message.content} /> : null}
                  </article>
                ))
              ) : (
                <EmptyState
                  icon={<History size={26} aria-hidden="true" />}
                  title="还没有逐字稿"
                  desc="这一轮没有落库的消息记录，练习完一轮后逐字稿会出现在这里。"
                />
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {[
          { to: "/progress", icon: TrendingUp, title: "查看进度", desc: "长期画像与错误类型" },
          { to: "/history", icon: History, title: "全部历史", desc: "回看每一轮复盘" },
          { to: "/", icon: ArrowUpRight, title: "再来一轮", desc: "换一个场景继续练" },
        ].map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="card-lift group rounded-[24px] border border-[#131311]/8 bg-white p-5"
          >
            <item.icon size={20} className="text-stone-400 transition group-hover:text-[#131311]" aria-hidden="true" />
            <p className="font-display mt-2 text-[16px] font-bold">{item.title}</p>
            <p className="text-[12px] text-stone-400">{item.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
