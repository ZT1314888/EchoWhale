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
    if (!activeId) {
      setDetail(null);
      setMessages([]);
      setHasMoreReplay(false);
      setNextReplayCursor(null);
      return;
    }

    let alive = true;
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
