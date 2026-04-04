import { useEffect, useState } from "react";

import { BrandHeader } from "../components/BrandHeader";
import { HistoryDetailPanel } from "../components/HistoryDetailPanel";
import { HistoryList } from "../components/HistoryList";
import { getHistorySession, listHistorySessions } from "../services/mockApi";
import type { HistoryDetail, HistoryEntry } from "../types/app";

export function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    listHistorySessions()
      .then((value) => {
        if (!alive) {
          return;
        }

        setEntries(value);
        setActiveId(value[0]?.id ?? "");
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

  useEffect(() => {
    if (!activeId) {
      return;
    }

    let alive = true;

    getHistorySession(activeId)
      .then((value) => {
        if (alive) {
          setDetail(value);
        }
      })
      .catch((reason: { message?: string }) => {
        if (alive) {
          setError(reason.message ?? "复盘详情加载失败。");
        }
      });

    return () => {
      alive = false;
    };
  }, [activeId]);

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
              <HistoryList entries={entries} activeId={activeId} onSelect={setActiveId} />
            ) : (
              <section className="panel-card panel-card--soft empty-state">
                <h2>还没有历史记录</h2>
                <p className="muted-text">完成第一轮图片练习后，这里会出现你的复盘列表。</p>
              </section>
            )}
          </section>

          {detail ? (
            <HistoryDetailPanel detail={detail} />
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
