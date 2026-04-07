import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Logo } from "../components/Logo";
import { useDeepgramVoiceAgent } from "../hooks/useDeepgramVoiceAgent";
import { getPracticeSession } from "../services/practiceApi";
import { bootstrapVoiceSession, completeVoiceSession } from "../services/sessionApi";
import type { SessionSummary } from "../types/app";

export function PracticeSessionPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState("");
  const [ending, setEnding] = useState(false);
  const [conversationStarted, setConversationStarted] = useState(false);
  const voice = useDeepgramVoiceAgent();

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

  async function onStartConversation() {
    try {
      setError("");
      const bootstrap = await bootstrapVoiceSession(sessionId);
      setSession(bootstrap.session);
      await voice.startSession(bootstrap);
      setConversationStarted(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "语音会话启动失败，请稍后再试。");
      setConversationStarted(false);
    }
  }

  async function onEndConversation() {
    try {
      setError("");
      setEnding(true);
      const result = await voice.endSession();
      if (!result.conversation.length) {
        setError("还没有识别到有效语音内容，先说一句再结束本次练习。");
        return;
      }
      await completeVoiceSession(sessionId, {
        conversation: result.conversation,
        terminationReason: result.terminationReason,
        clientDiagnostics: result.clientDiagnostics,
      });
      setConversationStarted(false);
      navigate(`/session/${sessionId}/review`);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "语音会话结束失败，请稍后再试。");
    } finally {
      setEnding(false);
    }
  }

  if (error && !session) {
    return (
      <div className="page-shell page-shell--session-immersive">
        <main className="session-stage session-stage--empty">
          <section className="session-console session-console--empty">
            <h1>练习暂时不可用</h1>
            <p className="muted-text">{error}</p>
            <Link className="primary-button session-cta-button" to="/">
              返回首页
            </Link>
          </section>
        </main>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="page-shell page-shell--session-immersive">
        <main className="session-stage session-stage--empty">
          <section className="session-console session-console--empty">
            <h1>正在准备练习会话…</h1>
          </section>
        </main>
      </div>
    );
  }

  const isLive =
    conversationStarted || voice.isConnected || voice.isListening || voice.isThinking || voice.isSpeaking;
  const roleTitle = session.roleLabel.replace(/^角色 · /, "");
  const supportingCopy = conversationStarted
    ? "语音会话已连接。你可以直接开口，系统会实时显示对话内容。"
    : `你正在和 ${roleTitle} 进行一段英语陪练。点击按钮后开始连续语音，直到手动结束本次会话。`;
  const statusLabel = ending
    ? "Ending"
    : voice.isSpeaking
      ? "Speaking"
      : voice.isThinking
        ? "Thinking"
        : isLive
          ? "Listening"
          : "Ready";
  const statusToneClass = ending
    ? "session-status-pill--ending"
    : voice.isSpeaking || voice.isThinking || isLive
      ? "session-status-pill--live"
      : "session-status-pill--ready";

  return (
    <div className="page-shell page-shell--session-immersive">
      <main className="session-stage">
        <section className={`session-hero${isLive ? " session-hero--live" : ""}`}>
          <div className="session-logo-cluster" aria-hidden="true">
            <span className="session-logo-ring session-logo-ring--outer" />
            <span className="session-logo-ring session-logo-ring--mid" />
            <span className="session-logo-ring session-logo-ring--inner" />
            <div className="session-logo-mark">
              <Logo className="session-logo-svg" title="" />
            </div>
          </div>
          <div className="session-hero-copy">
            <p className="eyebrow eyebrow--brand">Voice Practice Session</p>
            <h1>{session.title}</h1>
            <p className="session-hero-text">{supportingCopy}</p>
            <p className="session-hero-prompt">{session.openingPrompt}</p>
            <div className="session-tag-row">
              {session.tags.map((tag) => (
                <span key={tag} className="session-tag">
                  {tag}
                </span>
              ))}
            </div>
            <div className="session-hero-actions">
              {conversationStarted ? (
                <button
                  className="ghost-button session-cta-button session-cta-button--end"
                  type="button"
                  onClick={onEndConversation}
                  disabled={ending}
                >
                  {ending ? "Ending…" : "End Conversation"}
                </button>
              ) : (
                <button className="primary-button session-cta-button" type="button" onClick={onStartConversation}>
                  Talk To Your Agent
                </button>
              )}
            </div>
            {voice.error || error ? <p className="session-inline-error">{voice.error || error}</p> : null}
          </div>
        </section>

        <section className={`session-console${isLive ? " session-console--live" : ""}`}>
          <div className="session-console-header">
            <div>
              <p className="eyebrow">Conversation Feed</p>
              <h2>{roleTitle}</h2>
            </div>
            <span className={`session-status-pill ${statusToneClass}`}>{statusLabel}</span>
          </div>

          <div className="session-thread" role="log" aria-live="polite">
            {session.messages.map((message) => (
              <article
                key={message.id}
                className={
                  message.role === "learner"
                    ? "session-bubble session-bubble--learner"
                    : "session-bubble session-bubble--coach"
                }
              >
                <p className="eyebrow">{message.label}</p>
                <p>{message.content}</p>
              </article>
            ))}
            {voice.transcript.map((message, index) => (
              <article
                key={`live-${message.role}-${index}`}
                className={
                  message.role === "user"
                    ? "session-bubble session-bubble--learner session-bubble--live"
                    : "session-bubble session-bubble--coach session-bubble--live"
                }
              >
                <p className="eyebrow">{message.role === "user" ? "你 · 实时转写" : "Agent · 实时回复"}</p>
                <p>{message.content}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
