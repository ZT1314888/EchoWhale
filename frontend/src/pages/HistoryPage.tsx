import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Mic, Search, SlidersHorizontal, X } from "lucide-react";

import { HistoryDetailPanel } from "../components/HistoryDetailPanel";
import { HistoryList } from "../components/HistoryList";
import { PageShell } from "../components/ui";
import {
  getHistorySession,
  getHistorySessionMessages,
  listHistorySessions,
} from "../services/historyApi";
import type { HistoryDetail, HistoryEntry, PracticeMessage } from "../types/app";
import {
  filterHistory,
  searchHistory,
  sortHistory,
  summarizeHistory,
  type HistoryFilter,
  type HistorySort,
} from "../utils/historyStats";

const HISTORY_PAGE_SIZE = 20;
const REPLAY_PAGE_SIZE = 20;

const FILTERS: { id: HistoryFilter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "completed", label: "已完成" },
  { id: "active", label: "进行中" },
];

export function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [messages, setMessages] = useState<PracticeMessage[]>([]);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const [sort, setSort] = useState<HistorySort>("newest");
  const [nextHistoryCursor, setNextHistoryCursor] = useState<string | null>(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [loadingMoreHistory, setLoadingMoreHistory] = useState(false);
  const [nextReplayCursor, setNextReplayCursor] = useState<string | null>(null);
  const [hasMoreReplay, setHasMoreReplay] = useState(false);
  const [loadingMoreReplay, setLoadingMoreReplay] = useState(false);

  // 退出选中（activeId 清空）时清掉详情态。用"渲染期调整 state"模式（React 官方
  // 推荐替代 effect 重置）：同一渲染内完成清空，避免先渲染一帧旧详情再级联重渲。
  // prevActiveId 无条件跟踪变化，保证"空→id→空"往返时第二次也能正确清空；
  // activeId 在非空 id 之间的切换不走这里，由下方的拉取 effect 用新数据替换。
  const [prevActiveId, setPrevActiveId] = useState(activeId);
  if (prevActiveId !== activeId) {
    setPrevActiveId(activeId);
    if (!activeId) {
      setDetail(null);
      setMessages([]);
      setHasMoreReplay(false);
      setNextReplayCursor(null);
    }
  }

  useEffect(() => {
    let alive = true;

    listHistorySessions({ limit: HISTORY_PAGE_SIZE })
      .then((value) => {
        if (!alive) {
          return;
        }
        setEntries(value.items);
        setHasMoreHistory(value.page.hasMore);
        setNextHistoryCursor(value.page.nextCursor);
        setActiveId(value.items[0]?.id ?? "");
      })
      .catch((reason: { message?: string }) => {
        if (alive) {
          setError(reason.message ?? "历史记录加载失败。");
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  async function loadMoreHistory() {
    if (!hasMoreHistory || !nextHistoryCursor || loadingMoreHistory) {
      return;
    }
    setLoadingMoreHistory(true);
    try {
      const value = await listHistorySessions({
        limit: HISTORY_PAGE_SIZE,
        cursor: nextHistoryCursor,
      });
      setEntries((previous) => mergeHistoryEntries(previous, value.items));
      setHasMoreHistory(value.page.hasMore);
      setNextHistoryCursor(value.page.nextCursor);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "历史记录加载失败。");
    } finally {
      setLoadingMoreHistory(false);
    }
  }

  useEffect(() => {
    // 空 activeId 时不清状态也不拉取：清空已由上方渲染期重置完成。
    if (!activeId) {
      return;
    }

    let alive = true;
    // 拉取开始时同步置 loading：loadingReplay 是本次请求的即时反馈（外部请求
    // 生命周期的同步镜像），放到异步回调里会出现"无 loading 空窗"。
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 见上：请求生命周期的同步镜像
    setLoadingMoreReplay(true);

    Promise.all([
      getHistorySession(activeId),
      getHistorySessionMessages(activeId, { limit: REPLAY_PAGE_SIZE }),
    ])
      .then(([nextDetail, replayPage]) => {
        if (!alive) {
          return;
        }
        setDetail(nextDetail);
        setMessages(replayPage.items);
        setHasMoreReplay(replayPage.page.hasMore);
        setNextReplayCursor(replayPage.page.nextCursor);
      })
      .catch((reason: { message?: string }) => {
        if (alive) {
          setError(reason.message ?? "复盘详情加载失败。");
        }
      })
      .finally(() => {
        if (alive) {
          setLoadingMoreReplay(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [activeId]);

  async function loadMoreReplayMessages() {
    if (!activeId || !hasMoreReplay || !nextReplayCursor || loadingMoreReplay) {
      return;
    }
    setLoadingMoreReplay(true);
    try {
      const replayPage = await getHistorySessionMessages(activeId, {
        limit: REPLAY_PAGE_SIZE,
        cursor: nextReplayCursor,
      });
      setMessages((previous) => mergeReplayMessages(replayPage.items, previous));
      setHasMoreReplay(replayPage.page.hasMore);
      setNextReplayCursor(replayPage.page.nextCursor);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "消息回放加载失败。");
    } finally {
      setLoadingMoreReplay(false);
    }
  }

  const stats = summarizeHistory(entries);
  const visibleEntries = useMemo(
    () => sortHistory(searchHistory(filterHistory(entries, filter), keyword), sort),
    [entries, filter, keyword, sort],
  );

  return (
    <PageShell wide>
      <div className="flex flex-wrap items-end justify-between gap-4">
        {/* 标题是 h1：路由级测试用 getByRole("heading", { level: 1, name: /练习历史/i })
            匹配，所以可访问名必须是中文原文 —— 可见的英文标题行整体 aria-hidden。 */}
        <div className="max-w-2xl">
          <h1 className="font-display text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]">
            <span className="sr-only">练习历史</span>
            <span aria-hidden="true">
              The archive
              <span className="font-serif-accent ml-2 align-middle text-[0.62em] font-medium text-stone-400">
                练习历史
              </span>
            </span>
          </h1>
          <p className="mt-2 text-[13.5px] leading-relaxed text-stone-500">
            每一轮练习都落在这里：逐字稿、反馈摘要与场景标签，随时回看。
          </p>
        </div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 rounded-full bg-[#131311] px-5 py-3 text-[13px] font-bold text-white transition hover:bg-black"
        >
          <Mic size={15} className="text-[#d8f34e]" aria-hidden="true" />
          开始新练习
        </Link>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-[28px] border border-[#131311]/8 bg-[#131311]/8 lg:grid-cols-4">
        {[
          [String(stats.loadedSessions), "Loaded", "已加载"],
          [String(stats.completedSessions), "Completed", "已完成"],
          ["—", "Avg. score", "平均分"],
          ["—", "Words", "总词数"],
        ].map(([value, label, cn]) => (
          <div key={label} className="bg-[#faf9f6] p-6">
            <p className="font-display text-[32px] font-bold tracking-tight">{value}</p>
            <p className="mt-0.5 text-[12px] font-bold">
              {label} <span className="font-normal text-stone-400">{cn}</span>
            </p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-stone-400">
        「已加载 / 已完成」统计的是当前已加载的条目；平均分与词数后端没有对应字段。
      </p>

      <div className="glass sticky top-[68px] z-30 mt-5 flex flex-col gap-3 rounded-[24px] border border-[#131311]/8 bg-[#f4f3ef]/90 p-3 lg:flex-row lg:items-center">
        <div className="flex flex-1 items-center gap-2.5 rounded-2xl border border-[#131311]/8 bg-white px-4 py-3">
          <Search size={16} className="shrink-0 text-stone-400" aria-hidden="true" />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            aria-label="搜索练习历史"
            placeholder="搜索场景标题、角色或标签…"
            className="w-full bg-transparent text-[13.5px] font-medium outline-none placeholder:text-stone-400"
          />
          {keyword ? (
            <button
              type="button"
              onClick={() => setKeyword("")}
              aria-label="清空搜索"
              className="text-stone-400 transition hover:text-[#131311]"
            >
              <X size={15} aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <div className="flex gap-1 rounded-2xl border border-[#131311]/8 bg-white p-1">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              aria-pressed={filter === item.id}
              className={`rounded-xl px-3.5 py-2 text-[12.5px] font-bold transition ${
                filter === item.id ? "bg-[#131311] text-white" : "text-stone-400 hover:text-[#131311]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setSort(sort === "newest" ? "oldest" : "newest")}
          className="flex items-center justify-center gap-1.5 rounded-2xl border border-[#131311]/8 bg-white px-4 py-3 text-[12.5px] font-bold transition hover:border-[#131311]"
        >
          <SlidersHorizontal size={14} aria-hidden="true" />
          {sort === "newest" ? "最新在前" : "最早在前"}
        </button>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,340px)_1fr]">
        <section>
          {error && !entries.length ? (
            <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] font-semibold text-rose-700">
              {error}
            </p>
          ) : null}

          {!entries.length && !error ? (
            <div className="rounded-[28px] border border-dashed border-[#131311]/15 bg-white/60 p-10 text-center">
              <span className="mx-auto grid h-14 w-14 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">
                <Mic size={22} aria-hidden="true" />
              </span>
              <h2 className="font-display mt-4 text-lg font-bold">还没有历史记录</h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-stone-500">
                完成第一轮练习后，这里会出现你的复盘列表。
              </p>
              <Link
                to="/"
                className="mt-5 inline-flex items-center gap-2 rounded-full bg-[#131311] px-6 py-3 text-[13px] font-bold text-white"
              >
                上传图片开始第一次练习
                <ArrowUpRight size={15} className="text-[#d8f34e]" aria-hidden="true" />
              </Link>
            </div>
          ) : null}

          {entries.length && !visibleEntries.length ? (
            <div className="rounded-[28px] border border-dashed border-[#131311]/15 bg-white/60 p-10 text-center">
              <h2 className="font-display text-lg font-bold">没有匹配的记录</h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-stone-500">换个关键词或筛选条件试试。</p>
            </div>
          ) : null}

          {visibleEntries.length ? (
            <>
              <HistoryList entries={visibleEntries} activeId={activeId} onSelect={setActiveId} />
              {hasMoreHistory ? (
                <button
                  type="button"
                  disabled={loadingMoreHistory}
                  onClick={() => {
                    void loadMoreHistory();
                  }}
                  className="mt-3 w-full rounded-full border border-[#131311]/12 bg-white px-4 py-3 text-[12.5px] font-bold text-[#131311] transition hover:border-[#131311] disabled:opacity-50"
                >
                  {loadingMoreHistory ? "加载中..." : "加载更多历史"}
                </button>
              ) : null}
            </>
          ) : null}
        </section>

        {detail ? (
          <HistoryDetailPanel
            detail={detail}
            messages={messages}
            loadingReplay={loadingMoreReplay}
            hasMoreReplay={hasMoreReplay}
            onLoadMoreReplay={() => {
              void loadMoreReplayMessages();
            }}
          />
        ) : (
          <section className="rounded-[28px] border border-dashed border-[#131311]/15 bg-white/60 p-10 text-center">
            <h2 className="font-display text-lg font-bold">复盘详情</h2>
            <p className="mt-1.5 text-[13px] leading-relaxed text-stone-500">
              从左侧选择一轮练习，查看消息回放和反馈摘要。
            </p>
          </section>
        )}
      </div>
    </PageShell>
  );
}

function mergeHistoryEntries(previous: HistoryEntry[], incoming: HistoryEntry[]): HistoryEntry[] {
  const seen = new Set(previous.map((item) => item.id));
  const additions = incoming.filter((item) => !seen.has(item.id));
  return [...previous, ...additions];
}

function mergeReplayMessages(incoming: PracticeMessage[], previous: PracticeMessage[]): PracticeMessage[] {
  const seen = new Set(previous.map((item) => item.id));
  const prefix = incoming.filter((item) => !seen.has(item.id));
  return [...prefix, ...previous];
}
