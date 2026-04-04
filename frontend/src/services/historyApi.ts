import type { AppError, HistoryDetail, HistoryEntry, SessionSummary } from "../types/app";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type BackendSessionMessage = {
  message_id: string;
  role: string;
  text: string;
};

type BackendSession = {
  session_id: string;
  media_id: string;
  scene: string;
  role: string;
  opener: string;
  status: string;
  labels: string[];
  messages: BackendSessionMessage[];
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

type BackendHistoryEntry = {
  id: string;
  practiced_at: string;
  status: string;
  scene_title: string;
  role_label: string;
  preview: string;
  tags: string[];
  review_title: string;
  review_summary: string;
};

type BackendHistoryDetail = {
  entry: BackendHistoryEntry;
  session: BackendSession;
  review: BackendReviewSummary;
};

const SCENE_META: Record<string, { title: string; liveHint: string }> = {
  coffee_shop: {
    title: "咖啡店柜台点单",
    liveHint: "先用一句短句回应，再补一条细节，会更稳。",
  },
  office: {
    title: "办公室状态同步",
    liveHint: "先说结果，再说原因，会更像真实办公室沟通。",
  },
  travel: {
    title: "街头问路确认路线",
    liveHint: "先说目的地，再确认转弯位置，会更清楚。",
  },
  street: {
    title: "街头问路确认路线",
    liveHint: "先说目的地，再确认转弯位置，会更清楚。",
  },
  restaurant: {
    title: "餐厅点单练习",
    liveHint: "先说主需求，再补额外偏好，会更自然。",
  },
};

function toError(message: string, code = "HISTORY_API_FAILED"): AppError {
  return { code, message };
}

function toSessionSummary(session: BackendSession): SessionSummary {
  const sceneMeta = SCENE_META[session.scene] ?? {
    title: session.scene.replace(/_/g, " "),
    liveHint: "先回答主需求，再补一条细节，会更稳。",
  };

  return {
    id: session.session_id,
    title: sceneMeta.title,
    roleLabel: `角色 · ${session.role}`,
    openingPrompt: `开场提示：${session.opener}`,
    tags: session.labels,
    liveHint: sceneMeta.liveHint,
    voiceTitle: "点一下，用声音回答",
    voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
    messages: session.messages.map((message) => ({
      id: message.message_id,
      role: message.role === "user" ? "learner" : "coach",
      label: message.role === "user" ? "你 · 本轮回答" : "教练 · 追问",
      content: message.text,
    })),
  };
}

function toReviewSummary(review: BackendReviewSummary) {
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

function toHistoryEntry(entry: BackendHistoryEntry): HistoryEntry {
  return {
    id: entry.id,
    practicedAt: entry.practiced_at,
    status: entry.status,
    sceneTitle: entry.scene_title,
    roleLabel: entry.role_label,
    preview: entry.preview,
    tags: entry.tags,
    reviewTitle: entry.review_title,
    reviewSummary: entry.review_summary,
  };
}

export async function listHistorySessions(): Promise<HistoryEntry[]> {
  let response: Response;

  try {
    response = await fetch("/api/v1/history/sessions");
  } catch {
    throw toError("历史记录加载失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendHistoryEntry[]>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "历史记录加载失败。");
  }

  return payload.data.map(toHistoryEntry);
}

export async function getHistorySession(sessionId: string): Promise<HistoryDetail> {
  let response: Response;

  try {
    response = await fetch(`/api/v1/history/sessions/${sessionId}`);
  } catch {
    throw toError("复盘详情加载失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendHistoryDetail>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "复盘详情加载失败。");
  }

  return {
    entry: toHistoryEntry(payload.data.entry),
    session: toSessionSummary(payload.data.session),
    review: toReviewSummary(payload.data.review),
  };
}
