import { useEffect, useState } from "react";

import { BrandHeader } from "../components/BrandHeader";
import { HistoryDetailPanel } from "../components/HistoryDetailPanel";
import { HistoryList } from "../components/HistoryList";
import {
  getHistorySession,
  getHistorySessionMessages,
  listHistorySessions,
} from "../services/historyApi";
import type { HistoryDetail, HistoryEntry, PracticeMessage } from "../types/app";

const HISTORY_PAGE_SIZE = 20;
const REPLAY_PAGE_SIZE = 20;

export function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [messages, setMessages] = useState<PracticeMessage[]>([]);
  const [error, setError] = useState("");
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

  return (
    <div className="page-shell">
      <div className="page-frame">
        <BrandHeader />

        <main className="page-grid page-grid--history">
          <section className="panel-section">
            <div className="section-header">
              <div>
                <p className="eyebrow eyebrow--brand">History Review</p>
                <h1>练习历史</h1>
              </div>
            </div>

            {error && !entries.length ? <p className="form-error">{error}</p> : null}
            {entries.length ? (
              <>
                <HistoryList entries={entries} activeId={activeId} onSelect={setActiveId} />
                {hasMoreHistory ? (
                  <button
                    className="ghost-button"
                    type="button"
                    disabled={loadingMoreHistory}
                    onClick={() => {
                      void loadMoreHistory();
                    }}
                  >
                    {loadingMoreHistory ? "加载中..." : "加载更多历史"}
                  </button>
                ) : null}
              </>
            ) : (
              <section className="panel-card panel-card--soft empty-state">
                <h2>还没有历史记录</h2>
                <p className="muted-text">完成第一轮图片练习后，这里会出现你的复盘列表。</p>
              </section>
            )}
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
            <section className="history-detail empty-state">
              <h2>复盘详情</h2>
              <p className="muted-text">从左侧选择一轮练习，查看消息回放和反馈摘要。</p>
            </section>
          )}
        </main>
      </div>
    </div>
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
