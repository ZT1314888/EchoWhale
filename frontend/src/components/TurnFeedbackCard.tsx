import type { PracticeFeedback } from "../types/app";

type TurnFeedbackCardProps = {
  feedback: PracticeFeedback;
  compact?: boolean;
};

/** 本轮反馈卡：流式期间悬浮展示（无标题），落库后内联挂在消息下方（compact）。 */
export function TurnFeedbackCard({ feedback, compact = false }: TurnFeedbackCardProps) {
  const metrics = [feedback.grammar, feedback.moreNatural];

  return (
    <aside
      className={`rounded-2xl border border-[#131311]/8 bg-white p-4 ${
        compact ? "ml-4 max-w-[84%]" : "shadow-[0_12px_28px_-18px_rgba(19,19,17,0.35)]"
      }`}
      data-testid={compact ? "message-feedback-card" : "turn-feedback-card"}
    >
      {compact ? null : (
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#4f46e5]">本轮反馈</p>
      )}
      <div className={compact ? "space-y-2.5" : "mt-3 space-y-2.5"}>
        {metrics.map((metric) => (
          <div key={metric.title}>
            <p className="text-[12px] font-bold text-[#131311]">{metric.title}</p>
            <p className="text-[13px] leading-relaxed text-stone-500">{metric.body}</p>
          </div>
        ))}
        <div>
          <p className="text-[12px] font-bold text-[#131311]">{feedback.usefulWords.title}</p>
          <p className="text-[13px] leading-relaxed text-stone-500">
            {feedback.usefulWords.words.length
              ? feedback.usefulWords.words.join(" · ")
              : feedback.usefulWords.body}
          </p>
        </div>
        <div className="rounded-xl bg-[#d8f34e]/25 p-3">
          <p className="text-[12px] font-bold text-[#131311]">{feedback.nextStep.title}</p>
          <p className="text-[13px] leading-relaxed text-stone-600">{feedback.nextStep.body}</p>
        </div>
      </div>
    </aside>
  );
}
