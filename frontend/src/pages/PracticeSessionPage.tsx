import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Logo } from "../components/Logo";
import { TextComposer } from "../components/TextComposer";
import { TurnFeedbackCard } from "../components/TurnFeedbackCard";
import { useDeepgramVoiceAgent } from "../hooks/useDeepgramVoiceAgent";
import { getPracticeSession } from "../services/practiceApi";
import {
  bootstrapVoiceSession,
  completeVoiceSession,
  submitPracticeTurnStream,
} from "../services/sessionApi";
import type { PracticeFeedback, SessionSummary } from "../types/app";

type LogoVisualState = "idle" | "activating" | "live" | "ending";

export function PracticeSessionPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [conversationStarted, setConversationStarted] = useState(false);
  const [showActivationPulse, setShowActivationPulse] = useState(false);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const activationTimeoutRef = useRef<number | null>(null);
  const voice = useDeepgramVoiceAgent();
  const [textSending, setTextSending] = useState(false);
  const [liveLearnerContent, setLiveLearnerContent] = useState("");
  const [streamText, setStreamText] = useState("");
  const [turnFeedback, setTurnFeedback] = useState<PracticeFeedback | null>(null);

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

  useEffect(() => {
    const scrollIntoView = conversationEndRef.current?.scrollIntoView;
    if (typeof scrollIntoView === "function") {
      scrollIntoView.call(conversationEndRef.current, { block: "end" });
    }
  }, [session?.messages.length, voice.transcript.length, liveLearnerContent, streamText.length]);

  useEffect(() => {
    return () => {
      if (activationTimeoutRef.current !== null) {
        window.clearTimeout(activationTimeoutRef.current);
      }
    };
  }, []);

  function triggerActivationPulse() {
    if (activationTimeoutRef.current !== null) {
      window.clearTimeout(activationTimeoutRef.current);
    }
    setShowActivationPulse(true);
    activationTimeoutRef.current = window.setTimeout(() => {
      setShowActivationPulse(false);
      activationTimeoutRef.current = null;
    }, 900);
  }

  async function onStartConversation() {
    try {
      setError("");
      setStarting(true);
      triggerActivationPulse();
      const bootstrap = await bootstrapVoiceSession(sessionId);
      setSession(bootstrap.session);
      await voice.startSession(bootstrap);
      setConversationStarted(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "语音会话启动失败，请稍后再试。");
      setConversationStarted(false);
    } finally {
      setStarting(false);
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

  async function onSendText(content: string, options: { signal: AbortSignal }) {
    setLiveLearnerContent(content);
    setStreamText("");
    setTurnFeedback(null);
    setError("");
    setTextSending(true);
    try {
      const result = await submitPracticeTurnStream(
        sessionId,
        { content },
        {
          onFeedback: (feedback) => setTurnFeedback(feedback),
          onDelta: (delta) => setStreamText((current) => current + delta),
        },
        options.signal,
      );
      setSession((current) => (current ? { ...current, messages: result.messages } : current));
      setLiveLearnerContent("");
      setStreamText("");
      // 落库后由消息自带 feedback 的内联卡片接棒，悬浮卡只负责流式期间。
      setTurnFeedback(null);
    } catch (reason) {
      const typed = reason as { name?: string; message?: string };
      if (typed?.name === "AbortError") {
        setLiveLearnerContent("");
        setStreamText("");
        setTurnFeedback(null);
      } else {
        setError(typed?.message ?? "发送失败，请稍后再试。");
      }
      throw reason;
    } finally {
      setTextSending(false);
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
  const statusLabel = ending
    ? "Ending"
    : textSending
      ? "Thinking"
      : voice.isSpeaking
        ? "Speaking"
        : voice.isThinking
          ? "Thinking"
          : isLive
            ? "Listening"
            : "Ready";
  const statusToneClass = ending
    ? "session-status-pill--ending"
    : textSending || voice.isSpeaking || voice.isThinking || isLive
      ? "session-status-pill--live"
      : "session-status-pill--ready";
  const logoVisualState: LogoVisualState = ending
    ? "ending"
    : isLive
        ? "live"
        : starting || showActivationPulse
          ? "activating"
        : "idle";
  const logoButtonLabel = ending
    ? "Ending voice practice"
    : isLive
      ? "End voice practice"
      : starting
        ? "Connecting voice practice"
        : "Start voice practice";

  return (
    <div className="page-shell page-shell--session-immersive">
      <main className="session-stage">
        <section className={`session-aside session-aside--${logoVisualState}`} data-testid="session-aside">
          <div className="session-aside-sticky">
            <button
              className="session-logo-button"
              type="button"
              onClick={isLive ? onEndConversation : onStartConversation}
              disabled={starting || ending || textSending}
              aria-label={logoButtonLabel}
              data-state={logoVisualState}
            >
              <span className="session-logo-ring session-logo-ring--outer" aria-hidden="true" />
              <span className="session-logo-ring session-logo-ring--mid" aria-hidden="true" />
              <span className="session-logo-ring session-logo-ring--inner" aria-hidden="true" />
              <span className="session-logo-aura" aria-hidden="true" />
              <span className="session-logo-mark" aria-hidden="true">
                <Logo className="session-logo-svg" title="" />
              </span>
            </button>
          </div>
        </section>

        <section
          className={`session-console${isLive ? " session-console--live" : ""}`}
          data-testid="session-conversation-panel"
        >
          <div className="session-console-header">
            <div className="session-console-heading">
              <p className="eyebrow eyebrow--brand">Voice Practice Session</p>
              <h1>{session.title}</h1>
              <p className="session-console-meta">{roleTitle}</p>
            </div>
            <span className={`session-status-pill ${statusToneClass}`}>{statusLabel}</span>
          </div>
          {voice.error || error ? <p className="session-inline-error session-inline-error--console">{voice.error || error}</p> : null}

          <div className="session-thread" role="log" aria-live="polite">
            {session.messages.map((message) => (
              <Fragment key={message.id}>
                <article
                  className={
                    message.role === "learner"
                      ? "session-bubble session-bubble--learner"
                      : "session-bubble session-bubble--coach"
                  }
                >
                  <p className="eyebrow">{message.label}</p>
                  <p>{message.content}</p>
                </article>
                {message.feedback ? <TurnFeedbackCard feedback={message.feedback} compact /> : null}
              </Fragment>
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
            {liveLearnerContent ? (
              <article
                className="session-bubble session-bubble--learner session-bubble--live"
                data-testid="learner-live-bubble"
              >
                <p className="eyebrow">你 · 本轮回答</p>
                <p>{liveLearnerContent}</p>
              </article>
            ) : null}
            {turnFeedback ? <TurnFeedbackCard feedback={turnFeedback} /> : null}
            {streamText ? (
              <article
                className="session-bubble session-bubble--coach session-bubble--live"
                data-testid="coach-stream-bubble"
              >
                <p className="eyebrow">教练 · 正在回复</p>
                <p>{streamText}</p>
              </article>
            ) : null}
            <div ref={conversationEndRef} aria-hidden="true" />
          </div>

          <TextComposer disabled={starting || ending} onSend={onSendText} />
        </section>
      </main>
    </div>
  );
}
