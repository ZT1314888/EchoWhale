import type { AppError, ReviewSummary } from "../types/app";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type BackendReviewFeedback = {
  grammar: { title: string; body: string };
  more_natural: { title: string; body: string };
  useful_words: { title: string; words: string[]; body: string };
  next_step: { title: string; body: string };
};

type BackendReviewSummary = {
  session_id: string;
  title: string;
  highlight: string;
  next_try: string;
  feedback: BackendReviewFeedback;
};

function toError(message: string, code = "REVIEW_API_FAILED"): AppError {
  return { code, message };
}

function toReviewSummary(review: BackendReviewSummary): ReviewSummary {
  return {
    sessionId: review.session_id,
    title: review.title,
    highlight: review.highlight,
    nextTry: review.next_try,
    feedback: {
      grammar: review.feedback.grammar,
      moreNatural: review.feedback.more_natural,
      usefulWords: review.feedback.useful_words,
      nextStep: review.feedback.next_step,
    },
  };
}

export async function getPracticeReview(sessionId: string): Promise<ReviewSummary> {
  let response: Response;

  try {
    response = await fetch(`/api/v1/sessions/${sessionId}/review`);
  } catch {
    throw toError("读取练后反馈失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendReviewSummary>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "读取练后反馈失败。");
  }

  return toReviewSummary(payload.data);
}
