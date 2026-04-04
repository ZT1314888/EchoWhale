import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
import { getPracticeSession, submitPracticeTurn } from "../services/practiceApi";
import type { PracticeFeedback, SessionSummary } from "../types/app";

export function PracticeSessionPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState<PracticeFeedback | null>(null);

  useEffect(() => {
    let alive = true;

    getPracticeSession(sessionId)
      .then((value) => {
        if (alive) {
          setSession(value);
        }
      })
      .catch((reason: { message?: string }) => {
        if (alive) {
          setError(reason.message ?? "加载练习会话失败。");
        }
      });

    return () => {
      alive = false;
    };
  }, [sessionId]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSending(true);

    try {
      const result = await submitPracticeTurn(sessionId, { content: draft });

      setSession((current) => (current ? { ...current, messages: result.messages } : current));
      setFeedback(result.feedback);
      setDraft("");
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "发送失败，请稍后再试。");
    } finally {
      setSending(false);
    }
  }

  if (error && !session) {
    return (
      <div className="page-shell">
        <div className="page-frame">
          <BrandHeader />
          <main className="empty-stage">
            <h1>练习暂时不可用</h1>
            <p className="muted-text">{error}</p>
            <Link className="primary-button" to="/">
              返回首页
            </Link>
          </main>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="page-shell">
        <div className="page-frame">
          <BrandHeader />
          <main className="empty-stage">
            <h1>正在准备练习会话…</h1>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="page-frame">
        <BrandHeader />

        <main className="page-grid page-grid--session">
          <section className="panel-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">Practice Session</p>
                <h2>练习会话</h2>
              </div>
              <span className="info-pill">语音优先模式</span>
            </div>

            <article className="panel-card panel-card--soft">
              <p className="eyebrow">场景速写</p>
              <h3>{session.title}</h3>
              <p className="scene-role">{session.roleLabel}</p>
              <p className="muted-text">{session.openingPrompt}</p>
              <div className="pill-row">
                {session.tags.map((tag) => (
                  <span key={tag} className="info-pill">
                    {tag}
                  </span>
                ))}
              </div>
            </article>

            <section className="message-stack">
              {session.messages.map((message) => (
                <article
                  key={message.id}
                  className={message.role === "learner" ? "message-card message-card--learner" : "message-card"}
                >
                  <p className="eyebrow">{message.label}</p>
                  <p>{message.content}</p>
                </article>
              ))}
            </section>

            <section className="panel-card voice-dock">
              <p className="eyebrow">语音底座</p>
              <div className="voice-row">
                <button className="mic-button" type="button">
                  开口
                </button>
                <div>
                  <h3>{session.voiceTitle}</h3>
                  <p className="muted-text">{session.voiceBody}</p>
                </div>
              </div>

              <form className="composer" onSubmit={onSubmit}>
                <label className="field-label" htmlFor="practice-input">
                  文本补充
                </label>
                <textarea
                  id="practice-input"
                  className="input-field input-field--textarea"
                  placeholder="先写一句英文回答，再补第二句细节。"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
                {error ? <p className="form-error">{error}</p> : null}
                <div className="action-row">
                  <button className="primary-button" type="submit" disabled={sending}>
                    {sending ? "发送中…" : "发送回答"}
                  </button>
                  <button className="ghost-button" type="button" onClick={() => navigate(`/session/${sessionId}/review`)}>
                    查看练后反馈
                  </button>
                </div>
              </form>
            </section>

            {feedback ? (
              <section className="review-grid">
                <article className="metric-card">
                  <h3>{feedback.grammar.title}</h3>
                  <p>{feedback.grammar.body}</p>
                </article>
                <article className="metric-card">
                  <h3>{feedback.moreNatural.title}</h3>
                  <p>{feedback.moreNatural.body}</p>
                </article>
              </section>
            ) : null}
          </section>

          <aside className="panel-card panel-card--soft side-note">
            <p className="eyebrow">即时提示</p>
            <p>{session.liveHint}</p>
          </aside>
        </main>
      </div>
    </div>
  );
}