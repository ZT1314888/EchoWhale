import { Link } from "react-router-dom";

import type { HistoryDetail } from "../types/app";

type HistoryDetailPanelProps = {
  detail: HistoryDetail;
};

export function HistoryDetailPanel({ detail }: HistoryDetailPanelProps) {
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
        <div className="message-stack message-stack--compact">
          {detail.session.messages.map((message) => (
            <article
              key={message.id}
              className={message.role === "learner" ? "message-card message-card--learner" : "message-card"}
            >
              <p className="eyebrow">{message.label}</p>
              <p>{message.content}</p>
            </article>
          ))}
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
