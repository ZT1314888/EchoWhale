import { useState } from "react";
import { Link } from "react-router-dom";
import { RotateCcw, Sparkles } from "lucide-react";

import { SpeakButton } from "./SpeakButton";
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

  const totalMessages = detail.session.totalMessages ?? messages.length;

  return (
    <section className="rounded-[28px] border border-[#131311]/8 bg-[#faf9f6] p-6" data-testid="history-detail">
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* h2 的可访问名必须是「复盘详情」（路由测试按 level 2 精确匹配），
            英文小标题单独占一行，不并进标题文本。 */}
        <div className="max-w-2xl">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#4f46e5]">Review</p>
          <h2 className="font-display mt-1 text-[24px] font-bold tracking-tight">复盘详情</h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-stone-500">{detail.entry.reviewTitle}</p>
        </div>
        <Link
          to={`/session/${detail.session.id}`}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#131311] px-5 py-3 text-[13px] font-bold text-white transition hover:bg-black"
        >
          <RotateCcw size={15} className="text-[#d8f34e]" aria-hidden="true" />
          再次练习
        </Link>
      </div>

      <article className="mt-5 rounded-[24px] border border-[#131311]/8 bg-white p-5">
        <h3 className="font-display text-[17px] font-bold tracking-tight">{detail.entry.sceneTitle}</h3>
        <p className="mt-0.5 text-[12px] text-stone-400">{detail.entry.roleLabel}</p>
        <p className="mt-2 text-[13.5px] leading-relaxed text-stone-600">{detail.entry.reviewSummary}</p>
        {detail.entry.tags.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {detail.entry.tags.map((tag) => (
              <span key={tag} className="rounded-full bg-stone-100 px-2.5 py-1 text-[11px] font-semibold text-stone-500">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </article>

      <article className="mt-4 rounded-[24px] border border-[#131311]/8 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-[13px] font-bold text-[#131311]">消息回放</h3>
            <p className="mt-0.5 text-[12px] text-stone-400">已加载 {messages.length} / 共 {totalMessages} 条消息</p>
          </div>
          {hasMoreReplay ? (
            <button
              type="button"
              disabled={loadingReplay}
              onClick={onLoadMoreReplay}
              className="rounded-full border border-[#131311]/12 bg-white px-4 py-2 text-[12.5px] font-bold text-[#131311] transition hover:border-[#131311] disabled:opacity-50"
            >
              {loadingReplay ? "加载中..." : "加载更早消息"}
            </button>
          ) : null}
        </div>

        <div className="mt-4 space-y-3">
          {messages.map((message) => (
            <article
              key={message.id}
              className={`rounded-2xl p-4 ${
                message.role === "learner"
                  ? "bg-[#131311] text-white"
                  : "border border-[#131311]/8 bg-[#faf9f6]"
              }`}
            >
              <p
                className={`text-[11px] font-bold uppercase tracking-[0.14em] ${
                  message.role === "learner" ? "text-[#d8f34e]" : "text-[#4f46e5]"
                }`}
              >
                {message.label}
              </p>
              <p className="mt-1.5 text-[13.5px] leading-relaxed">{toVisibleContent(message, expandedMessages[message.id] ?? false)}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {message.role === "coach" ? <SpeakButton text={message.content} compact /> : null}
                {shouldCollapseMessage(message) ? (
                  <button
                    type="button"
                    className={`text-[11.5px] font-bold underline decoration-2 underline-offset-4 ${
                      message.role === "learner"
                        ? "text-[#d8f34e] decoration-[#d8f34e]/40"
                        : "text-[#131311] decoration-[#d8f34e]"
                    }`}
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
              </div>
            </article>
          ))}
          {loadingReplay && !messages.length ? (
            <p className="text-[13px] text-stone-400">正在加载消息回放...</p>
          ) : null}
          {!loadingReplay && !messages.length ? (
            <p className="text-[13px] text-stone-400">这一轮还没有落库的消息。</p>
          ) : null}
        </div>
      </article>

      <article className="mt-4 rounded-[24px] border border-[#131311]/8 bg-white p-5">
        <p className="flex items-center gap-1.5 text-[13px] font-bold">
          <Sparkles size={14} className="text-[#4f46e5]" aria-hidden="true" />
          反馈摘要
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {[detail.review.feedback.grammar, detail.review.feedback.moreNatural].map((metric) => (
            <div key={metric.title} className="rounded-2xl bg-[#faf9f6] p-4">
              <p className="text-[12.5px] font-bold text-[#131311]">{metric.title}</p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-stone-500">{metric.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-2xl bg-[#d8f34e]/25 p-4">
          <p className="text-[12.5px] font-bold text-[#131311]">{detail.review.feedback.nextStep.title}</p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-stone-600">{detail.review.feedback.nextStep.body}</p>
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
