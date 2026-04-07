import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
import { getPracticeReview as getMockPracticeReview } from "../services/mockApi";
import { getPracticeReview as getRealPracticeReview } from "../services/reviewApi";
import type { ReviewSummary } from "../types/app";

export function PostPracticeReviewPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [review, setReview] = useState<ReviewSummary | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let alive = true;
    const loader =
      sessionId.startsWith("sess_") ? getRealPracticeReview : getMockPracticeReview;

    loader(sessionId)
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

  if (hasError && !review) {
    return (
      <div className="page-shell">
        <div className="page-frame">
          <BrandHeader />
          <main className="empty-stage">
            <h1>练后反馈还没准备好</h1>
            <Link className="primary-button" to={`/session/${sessionId}`}>
              返回练习
            </Link>
          </main>
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="page-shell">
        <div className="page-frame">
          <BrandHeader />
          <main className="empty-stage">
            <h1>正在生成练后反馈…</h1>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="page-frame">
        <BrandHeader />

        <main className="panel-section">
          <div className="section-header">
            <div>
              <p className="eyebrow">Review</p>
              <h2>练后反馈</h2>
            </div>
            <span className="info-pill">本轮回响</span>
          </div>

          <section className="panel-card review-hero">
            <h3>{review.title}</h3>
            <article className="panel-card panel-card--soft">
              <p className="eyebrow">最佳时刻</p>
              <p>{review.highlight}</p>
            </article>
            <article className="panel-card panel-card--soft">
              <p className="eyebrow">下一次尝试</p>
              <p>{review.nextTry}</p>
            </article>
          </section>

          <section className="review-grid review-grid--wide">
            <article className="metric-card">
              <h3>{review.feedback.grammar.title}</h3>
              <p>{review.feedback.grammar.body}</p>
            </article>
            <article className="metric-card">
              <h3>{review.feedback.moreNatural.title}</h3>
              <p>{review.feedback.moreNatural.body}</p>
            </article>
            <article className="metric-card">
              <h3>{review.feedback.usefulWords.title}</h3>
              <p>{review.feedback.usefulWords.words.join(" · ")}</p>
            </article>
            <article className="metric-card">
              <h3>{review.feedback.nextStep.title}</h3>
              <p>{review.feedback.nextStep.body}</p>
            </article>
          </section>

          <div className="action-row">
            <button className="primary-button" type="button" onClick={() => navigate(`/session/${sessionId}`)}>
              再练一轮
            </button>
            <Link className="ghost-button" to="/history">
              查看历史
            </Link>
            <Link className="ghost-button" to="/">
              返回首页
            </Link>
          </div>
        </main>
      </div>
    </div>
  );
}
