import { useState } from "react";
import { Link } from "react-router-dom";

import type { HistoryDetail, PracticeMessage } from "../types/app";

type HistoryDetailPanelProps = {
  detail: HistoryDetail;
  messages: PracticeMessage[];
  loadingReplay: boolean;
  hasMoreReplay: boolean;
  onLoadMoreReplay: () => void;
};

const MESSAGE_PREVIEW_LENGTH = 180;

export function HistoryDetailPanel({
  detail,
  messages,
  loadingReplay,
  hasMoreReplay,
  onLoadMoreReplay,
}: HistoryDetailPanelProps) {
  const [expandedMessages, setExpandedMessages] = useState<Record<string, boolean>>({});
  // 换一个会话详情时重置展开状态。用"渲染期调整 state"模式（React 官方推荐替代
  // effect 重置）：同一次渲染内完成重置，避免 effect 先渲染一帧旧展开态再级联重渲。
  const [renderedSessionId, setRenderedSessionId] = useState(detail.session.id);
  if (renderedSessionId !== detail.session.id) {
    setRenderedSessionId(detail.session.id);
    setExpandedMessages({});
  }

  return (
    <section className="history-detail">
      <div className="section-header">
        <div>
          <p className="eyebrow eyebrow--brand">复盘详情</p>
          <h2>复盘详情</h2>
          <p className="muted-text">{detail.entry.reviewTitle}</p>
        </div>
        <Link className="primary-button" to={`/session/${detail.session.id}`}>
          再次练习
        </Link>
      </div>

      <article className="panel-card panel-card--soft">
        <h3>{detail.entry.sceneTitle}</h3>
        <p className="muted-text">{detail.entry.reviewSummary}</p>
        <div className="pill-row">
          {detail.entry.tags.map((tag) => (
            <span key={tag} className="info-pill">
              {tag}
            </span>
          ))}
        </div>
      </article>

      <article className="panel-card panel-card--soft">
        <p className="eyebrow">消息回放</p>
        <p className="muted-text">共 {detail.session.totalMessages ?? messages.length} 条消息</p>
        {hasMoreReplay ? (
          <button className="ghost-button" type="button" disabled={loadingReplay} onClick={onLoadMoreReplay}>
            {loadingReplay ? "加载中..." : "加载更早消息"}
          </button>
        ) : null}
        <div className="message-stack message-stack--compact">
          {messages.map((message) => (
            <article
              key={message.id}
              className={message.role === "learner" ? "message-card message-card--learner" : "message-card"}
            >
              <p className="eyebrow">{message.label}</p>
              <p>{toVisibleContent(message, expandedMessages[message.id] ?? false)}</p>
              {shouldCollapseMessage(message) ? (
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => {
                    setExpandedMessages((previous) => ({
                      ...previous,
                      [message.id]: !previous[message.id],
                    }));
                  }}
                >
                  {expandedMessages[message.id] ? "收起" : "展开全文"}
                </button>
              ) : null}
            </article>
          ))}
          {loadingReplay && !messages.length ? <p className="muted-text">正在加载消息回放...</p> : null}
        </div>
      </article>

      <article className="panel-card panel-card--soft">
        <p className="eyebrow">反馈摘要</p>
        <div className="review-grid">
          <article className="metric-card">
            <h3>{detail.review.feedback.grammar.title}</h3>
            <p>{detail.review.feedback.grammar.body}</p>
          </article>
          <article className="metric-card">
            <h3>{detail.review.feedback.moreNatural.title}</h3>
            <p>{detail.review.feedback.moreNatural.body}</p>
          </article>
        </div>
      </article>
    </section>
  );
}

function shouldCollapseMessage(message: PracticeMessage): boolean {
  return message.content.length > MESSAGE_PREVIEW_LENGTH;
}

function toVisibleContent(message: PracticeMessage, expanded: boolean): string {
  if (!shouldCollapseMessage(message) || expanded) {
    return message.content;
  }
  return `${message.content.slice(0, MESSAGE_PREVIEW_LENGTH)}...`;
}
