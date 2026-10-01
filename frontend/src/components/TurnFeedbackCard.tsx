import type { PracticeFeedback } from "../types/app";

type TurnFeedbackCardProps = {
  feedback: PracticeFeedback;
  compact?: boolean;
};

export function TurnFeedbackCard({ feedback, compact = false }: TurnFeedbackCardProps) {
  return (
    <aside
      className={
        compact ? "session-feedback-card session-feedback-card--compact" : "session-feedback-card"
      }
      data-testid={compact ? "message-feedback-card" : "turn-feedback-card"}
    >
      {compact ? null : <p className="eyebrow">本轮反馈</p>}
      <div className="session-feedback-card__item">
        <p className="session-feedback-card__label">{feedback.grammar.title}</p>
        <p className="session-feedback-card__body">{feedback.grammar.body}</p>
      </div>
      <div className="session-feedback-card__item">
        <p className="session-feedback-card__label">{feedback.moreNatural.title}</p>
        <p className="session-feedback-card__body">{feedback.moreNatural.body}</p>
      </div>
      <div className="session-feedback-card__item">
        <p className="session-feedback-card__label">{feedback.usefulWords.title}</p>
        <p className="session-feedback-card__body">
          {feedback.usefulWords.words.length
            ? feedback.usefulWords.words.join(" · ")
            : feedback.usefulWords.body}
        </p>
      </div>
      <div className="session-feedback-card__item">
        <p className="session-feedback-card__label">{feedback.nextStep.title}</p>
        <p className="session-feedback-card__body">{feedback.nextStep.body}</p>
      </div>
    </aside>
  );
}
