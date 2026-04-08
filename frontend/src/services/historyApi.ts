import type {
  AppError,
  HistoryDetail,
  HistoryEntriesPage,
  HistoryEntry,
  HistoryReplayPage,
  PracticeMessage,
  SessionSummary,
} from "../types/app";
import { apiFetch } from "./apiClient";

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
  media_id: string | null;
  scene: string;
  role: string;
  opener: string;
  status: string;
  visual_anchors?: string[];
  vocab_candidates?: string[];
  labels?: string[];
  total_messages?: number;
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
  vocab_candidates?: string[];
  tags?: string[];
  review_title: string;
  review_summary: string;
};

type BackendHistoryDetail = {
  entry: BackendHistoryEntry;
  session: BackendSession;
  review: BackendReviewSummary;
};

type BackendCursorPage = {
  has_more: boolean;
  next_cursor: string | null;
};

type BackendHistoryListData = {
  items: BackendHistoryEntry[];
  page: BackendCursorPage;
};

type BackendHistoryReplayData = {
  items: BackendSessionMessage[];
  page: BackendCursorPage;
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

function toPracticeMessage(message: BackendSessionMessage): PracticeMessage {
  return {
    id: message.message_id,
    role: message.role === "user" ? "learner" : "coach",
    label: message.role === "user" ? "你 · 本轮回答" : "教练 · 追问",
    content: message.text,
  };
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
    tags: session.vocab_candidates ?? session.labels ?? [],
    liveHint: sceneMeta.liveHint,
    voiceTitle: "点一下，用声音回答",
    voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
    messages: [],
    totalMessages: session.total_messages ?? 0,
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
    tags: entry.vocab_candidates ?? entry.tags ?? [],
    reviewTitle: entry.review_title,
    reviewSummary: entry.review_summary,
  };
}

function toCursorPage(page: BackendCursorPage) {
  return {
    hasMore: page.has_more,
    nextCursor: page.next_cursor,
  };
}

type ListHistorySessionsOptions = {
  limit?: number;
  cursor?: string | null;
};

type ListHistoryMessagesOptions = {
  limit?: number;
  cursor?: string | null;
};

function toHistoryListPath(options: ListHistorySessionsOptions): string {
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const query = params.toString();
  return query ? `/api/v1/history/sessions?${query}` : "/api/v1/history/sessions";
}

function toHistoryReplayPath(sessionId: string, options: ListHistoryMessagesOptions): string {
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const query = params.toString();
  return query
    ? `/api/v1/history/sessions/${sessionId}/messages?${query}`
    : `/api/v1/history/sessions/${sessionId}/messages`;
}

export async function listHistorySessions(
  options: ListHistorySessionsOptions = {},
): Promise<HistoryEntriesPage> {
  let response: Response;

  try {
    response = await apiFetch(toHistoryListPath(options));
  } catch {
    throw toError("历史记录加载失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendHistoryListData>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "历史记录加载失败。");
  }

  return {
    items: payload.data.items.map(toHistoryEntry),
    page: toCursorPage(payload.data.page),
  };
}

export async function getHistorySession(sessionId: string): Promise<HistoryDetail> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/history/sessions/${sessionId}`);
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

export async function getHistorySessionMessages(
  sessionId: string,
  options: ListHistoryMessagesOptions = {},
): Promise<HistoryReplayPage> {
  let response: Response;

  try {
    response = await apiFetch(toHistoryReplayPath(sessionId, options));
  } catch {
    throw toError("消息回放加载失败。");
  }

  const payload = (await response.json()) as ApiResponse<BackendHistoryReplayData>;
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "消息回放加载失败。");
  }

  return {
    items: payload.data.items.map(toPracticeMessage),
    page: toCursorPage(payload.data.page),
  };
}
