import type { FeedbackModel } from "../data/mockSession";

export function FeedbackCard({ feedback }: { feedback: FeedbackModel }) {
  return (
    <aside className="space-y-4 rounded-[30px] border border-[var(--color-aqua)]/20 bg-[var(--color-panel-strong)] p-5 shadow-[0_22px_80px_rgba(13,21,42,0.35)]">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="eyebrow">Micro feedback</p>
          <h3 className="font-display text-2xl text-[var(--color-foam)]">Grammar rescue</h3>
        </div>
        <span className="signal-chip signal-chip--cool">Coach pass</span>
      </div>

      <div className="space-y-3 rounded-[24px] bg-black/15 p-4">
        <p className="eyebrow">Grammar</p>
        <p className="text-sm leading-7 text-[var(--color-mist)]">{feedback.grammar}</p>
      </div>

      <div className="space-y-3 rounded-[24px] bg-black/15 p-4">
        <p className="eyebrow">More natural</p>
        <p className="text-sm leading-7 text-[var(--color-foam)]">{feedback.moreNatural}</p>
      </div>

      <div className="space-y-3 rounded-[24px] bg-black/15 p-4">
        <p className="eyebrow">Useful words</p>
        <div className="flex flex-wrap gap-2">
          {feedback.usefulWords.map((item) => (
            <span key={item} className="tag-chip tag-chip--bright">
              {item}
            </span>
          ))}
        </div>
      </div>
    </aside>
  );
}
