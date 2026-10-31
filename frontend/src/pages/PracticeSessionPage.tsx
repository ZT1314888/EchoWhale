import { Fragment, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Bot, Flag, Hash, Mic, Send, Square } from "lucide-react";

import { Logo } from "../components/Logo";
import { PhraseBank } from "../components/PhraseBank";
import { QuickReplyChips } from "../components/QuickReplyChips";
import { SessionMeter } from "../components/SessionMeter";
import { SpeakButton } from "../components/SpeakButton";
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

/** 通用口语起句，不是从场景里推出来的内容 —— 只是「不知道怎么说」时的脚手架。 */
const SENTENCE_STARTERS = [
  "To be honest, I think…",
  "What I mean is…",
  "Let me give you an example…",
  "That reminds me of…",
  "I'd say that…",
];

const QUICK_REPLIES = [
  "Could you say that again?",
  "Let me think for a second.",
  "That sounds good to me.",
  "Could I ask one more thing?",
];

export function PracticeSessionPage() {
  const navigate = useNavigate();
  const { sessionId = "" } = useParams();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [conversationStarted, setConversationStarted] = useState(false);
  const [showActivationPulse, setShowActivationPulse] = useState(false);
  const [showPhraseBank, setShowPhraseBank] = useState(true);
  const [draft, setDraft] = useState("");
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
      <main className="mx-auto max-w-2xl px-4 py-20 text-center sm:px-6">
        <h1 className="font-display text-[26px] font-bold tracking-tight">练习暂时不可用</h1>
        <p className="mt-3 text-[13.5px] leading-relaxed text-stone-500">{error}</p>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#131311] px-6 py-3 text-[13px] font-bold text-white transition hover:bg-black"
        >
          <ArrowLeft size={15} aria-hidden="true" />
          返回首页
        </button>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="grid min-h-[70vh] place-items-center px-4">
        <div className="text-center">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">
            <Mic size={24} aria-hidden="true" />
          </span>
          <h1 className="font-display mt-4 text-lg font-bold">正在准备练习会话…</h1>
        </div>
      </main>
    );
  }

  // 已完成的会话不再可练习，直接落到复盘页（replace 保证后退不回到练习页）。
  if (session.status === "completed") {
    return <Navigate to={`/session/${sessionId}/review`} replace />;
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
    ? "bg-rose-500/15 text-rose-200"
    : textSending || voice.isSpeaking || voice.isThinking || isLive
      ? "bg-[#d8f34e] text-[#131311]"
      : "bg-white/10 text-white/70";
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
  const learnerTurns =
    session.messages.filter((message) => message.role === "learner").length +
    voice.transcript.filter((message) => message.role === "user").length;
  const inlineError = voice.error || error;
  const composerLocked = starting || ending;

  return (
    <div className="mx-auto grid max-w-7xl gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[1fr_340px]">
      <section
        className="flex min-h-[80vh] flex-col overflow-hidden rounded-[28px] border border-[#131311]/8 bg-[#faf9f6] shadow-[0_32px_64px_-32px_rgba(19,19,17,0.25)]"
        data-testid="session-conversation-panel"
      >
        <header className="noise relative bg-[#131311] px-5 py-4 text-white sm:px-6">
          <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-[#4f46e5]/40 blur-[70px]" />
          <div className="relative flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("/")}
              aria-label="返回首页选择场景"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/15 text-white/70 transition hover:bg-white/10 hover:text-white"
            >
              <ArrowLeft size={17} aria-hidden="true" />
            </button>
            <span className="relative hidden h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[#d8f34e] text-[#131311] sm:grid">
              <Bot size={22} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[15px] font-bold">{session.title}</h1>
              <p className="text-[11.5px] text-white/45">{roleTitle}</p>
            </div>
            <span className={`shrink-0 rounded-full px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.14em] ${statusToneClass}`}>
              {statusLabel}
            </span>
            <span className="hidden sm:block">
              <SessionMeter turnCount={learnerTurns} />
            </span>
          </div>
          {session.tags.length ? (
            <div className="no-scrollbar relative mt-3.5 flex items-center gap-2 overflow-x-auto">
              <span className="shrink-0 text-[11px] font-bold uppercase tracking-[0.16em] text-[#d8f34e]">
                场景关键词
              </span>
              {session.tags.map((tag) => (
                <span
                  key={tag}
                  className="flex shrink-0 items-center gap-1 rounded-full border border-white/12 bg-white/5 px-3 py-1.5 text-[11.5px] font-medium text-white/70"
                >
                  <Hash size={10} aria-hidden="true" />
                  {tag}
                </span>
              ))}
            </div>
          ) : null}
        </header>

        {inlineError ? (
          <p className="border-b border-rose-100 bg-rose-50 px-5 py-2.5 text-[12.5px] font-semibold text-rose-700 sm:px-6">
            {inlineError}
          </p>
        ) : null}

        <div
          className="flex-1 space-y-4 overflow-y-auto p-5 sm:p-6"
          style={{ maxHeight: "52vh", minHeight: "36vh" }}
          role="log"
          aria-live="polite"
        >
          {session.messages.map((message) => (
            <Fragment key={message.id}>
              <article className={`flex ${message.role === "learner" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[84%] ${
                    message.role === "learner"
                      ? "rounded-[20px] rounded-tr-md bg-[#131311] p-4 text-white shadow-lg"
                      : "rounded-[20px] rounded-tl-md border border-[#131311]/8 bg-white p-4 shadow-sm"
                  }`}
                >
                  <p className={`text-[11px] font-bold uppercase tracking-[0.14em] ${message.role === "learner" ? "text-[#d8f34e]" : "text-[#4f46e5]"}`}>
                    {message.label}
                  </p>
                  <p className="mt-1.5 text-[14.5px] leading-relaxed">{message.content}</p>
                  {message.role === "coach" ? <SpeakButton text={message.content} /> : null}
                </div>
              </article>
              {message.feedback ? <TurnFeedbackCard feedback={message.feedback} compact /> : null}
            </Fragment>
          ))}

          {voice.transcript.map((message, index) => (
            <article
              key={`live-${message.role}-${index}`}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[84%] ring-2 ring-[#4f46e5]/25 ${
                  message.role === "user"
                    ? "rounded-[20px] rounded-tr-md bg-[#131311] p-4 text-white shadow-lg"
                    : "rounded-[20px] rounded-tl-md border border-[#131311]/8 bg-white p-4 shadow-sm"
                }`}
              >
                <p className="text-[11px] font-bold uppercase tracking-[0.14em] opacity-70">
                  {message.role === "user" ? "你 · 实时转写" : "Agent · 实时回复"}
                </p>
                <p className="mt-1.5 text-[14.5px] leading-relaxed">{message.content}</p>
              </div>
            </article>
          ))}

          {liveLearnerContent ? (
            <article className="flex justify-end" data-testid="learner-live-bubble">
              <div className="max-w-[84%] rounded-[20px] rounded-tr-md bg-[#131311] p-4 text-white shadow-lg ring-2 ring-[#4f46e5]/25">
                <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#d8f34e]">你 · 本轮回答</p>
                <p className="mt-1.5 text-[14.5px] leading-relaxed">{liveLearnerContent}</p>
              </div>
            </article>
          ) : null}

          {turnFeedback ? <TurnFeedbackCard feedback={turnFeedback} /> : null}

          {streamText ? (
            <article className="flex justify-start" data-testid="coach-stream-bubble">
              <div className="max-w-[84%] rounded-[20px] rounded-tl-md border border-[#131311]/8 bg-white p-4 shadow-sm ring-2 ring-[#4f46e5]/25">
                <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#4f46e5]">教练 · 正在回复</p>
                <p className="mt-1.5 text-[14.5px] leading-relaxed">{streamText}</p>
              </div>
            </article>
          ) : null}

          <div ref={conversationEndRef} aria-hidden="true" />
        </div>

        <QuickReplyChips
          replies={QUICK_REPLIES}
          disabled={composerLocked || textSending}
          onPick={(reply) => void onSendText(reply, { signal: new AbortController().signal }).catch(() => undefined)}
        />

        <div className="border-t border-[#131311]/8 bg-white/70 p-4 sm:px-6">
          <TextComposer disabled={composerLocked} onSend={onSendText} draft={draft} onDraftChange={setDraft} />
          <p className="mt-2 text-center text-[11px] text-stone-400">
            每轮 2–3 句即可 · Enter 发送，Shift + Enter 换行
          </p>
        </div>
      </section>

      <aside className="flex flex-col gap-5" data-testid="session-aside">
        <section className="noise relative overflow-hidden rounded-[28px] bg-[#131311] p-5 text-white">
          <div className="pointer-events-none absolute -right-14 -top-14 h-40 w-40 rounded-full bg-[#4f46e5]/40 blur-[60px]" />
          <p className="relative text-[11px] font-bold uppercase tracking-[0.2em] text-white/45">
            语音练习 · Voice
          </p>
          <div className="relative mt-4 flex items-center gap-4">
            <button
              type="button"
              onClick={isLive ? onEndConversation : onStartConversation}
              disabled={starting || ending || textSending}
              aria-label={logoButtonLabel}
              data-state={logoVisualState}
              className={`relative grid h-[68px] w-[68px] shrink-0 place-items-center rounded-full transition disabled:opacity-60 ${
                logoVisualState === "live"
                  ? "bg-[#d8f34e] text-[#131311]"
                  : "bg-white/10 text-[#d8f34e] hover:bg-white/20"
              }`}
            >
              {(logoVisualState === "live" || logoVisualState === "activating") && (
                <>
                  <span className="animate-pulse-ring absolute inset-0 rounded-full border border-[#d8f34e]/70" aria-hidden="true" />
                  <span className="animate-pulse-ring absolute inset-0 rounded-full border border-[#d8f34e]/40" aria-hidden="true" />
                </>
              )}
              {isLive ? <Square size={22} className="relative fill-current" aria-hidden="true" /> : <Logo className="relative h-9 w-9" title="" />}
            </button>
            <div className="text-[12.5px] leading-relaxed text-white/60">
              {isLive ? (
                <>
                  <p className="font-bold text-white">练习进行中</p>
                  <p>点一下鲸鱼结束本轮，并生成复盘。</p>
                </>
              ) : (
                <>
                  <p className="font-bold text-white">准备开始</p>
                  <p>点一下鲸鱼开始语音对话，也可以用下方文字先热身。</p>
                </>
              )}
            </div>
          </div>
        </section>

        {showPhraseBank ? (
          <PhraseBank
            phrases={SENTENCE_STARTERS}
            onInsert={(phrase) => setDraft((current) => (current ? `${current} ${phrase} ` : `${phrase} `))}
            onDismiss={() => setShowPhraseBank(false)}
          />
        ) : null}

        <section className="rounded-[28px] border border-[#131311]/8 bg-white p-5">
          <h2 className="flex items-center gap-1.5 text-[13px] font-bold">
            <Flag size={15} className="text-[#131311]" aria-hidden="true" />
            本场概况
          </h2>
          <dl className="mt-3 space-y-2 text-[12.5px]">
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">角色</dt>
              <dd className="font-bold text-[#131311]">{roleTitle}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">已开口轮数</dt>
              <dd className="font-bold text-[#131311]">{learnerTurns}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">场景关键词</dt>
              <dd className="font-bold text-[#131311]">{session.tags.length}</dd>
            </div>
          </dl>
          <p className="mt-4 flex items-start gap-1.5 rounded-2xl bg-[#d8f34e]/25 p-3 text-[11.5px] leading-relaxed text-stone-600">
            <Send size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
            本轮结束前，记得回头看一遍复盘页的逐字稿。
          </p>
        </section>
      </aside>
    </div>
  );
}
