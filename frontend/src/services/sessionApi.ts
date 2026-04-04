import type {
  AppError,
  PracticeFeedback,
  PracticeMessage,
  PracticeTurnInput,
  SessionSummary,
  SubmitPracticeTurnResult,
} from "../types/app";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type BackendSessionMessage = {
  message_id: string;
  role: string;
  text: string;
  feedback?: {
    grammar: string;
    more_natural: string;
    useful_words: string[];
  } | null;
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

type BackendReplyFeedback = {
  grammar: string;
  more_natural: string;
  useful_words: string[];
};

type BackendReplyResponse = {
  session: BackendSession;
  feedback?: BackendReplyFeedback | null;
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
  restaurant: {
    title: "餐厅点单练习",
    liveHint: "先说主需求，再补额外偏好，会更自然。",
  },
};

function toError(message: string, code = "SESSION_API_FAILED"): AppError {
  return { code, message };
}

async function parseResponse<T>(response: Response): Promise<ApiResponse<T>> {
  return (await response.json()) as ApiResponse<T>;
}

function toPracticeMessage(message: BackendSessionMessage): PracticeMessage {
  const isLearner = message.role === "user";
  return {
    id: message.message_id,
    role: isLearner ? "learner" : "coach",
    label: isLearner ? "你 · 本轮回答" : "教练 · 追问",
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
    tags: session.labels,
    liveHint: sceneMeta.liveHint,
    voiceTitle: "点一下，用声音回答",
    voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
    messages: session.messages.map(toPracticeMessage),
  };
}

function toPracticeFeedback(feedback: BackendReplyFeedback | null | undefined): PracticeFeedback {
  return {
    grammar: {
      title: "Grammar",
      body: feedback?.grammar ?? "继续把主句说完整，会更清楚。",
    },
    moreNatural: {
      title: "More Natural",
      body: feedback?.more_natural ?? "先说主需求，再补充细节，会更自然。",
    },
    usefulWords: {
      title: "Useful Words",
      words: feedback?.useful_words ?? [],
      body: "把这些词带进下一轮回答，会更自然。",
    },
    nextStep: {
      title: "Next Step",
      body: "下一轮试着在一句主回应后再补一句细节。",
    },
  };
}

export async function createPracticeSession(mediaId: string): Promise<{ sessionId: string }> {
  let response: Response;

  try {
    response = await fetch("/api/v1/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ media_id: mediaId }),
    });
  } catch {
    throw toError("创建练习会话失败，请稍后重试。", "SESSION_START_FAILED");
  }

  const payload = await parseResponse<BackendSession>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "创建练习会话失败，请稍后重试。", "SESSION_START_FAILED");
  }

  return { sessionId: payload.data.session_id };
}

export async function getPracticeSession(sessionId: string): Promise<SessionSummary> {
  let response: Response;

  try {
    response = await fetch(`/api/v1/sessions/${sessionId}`);
  } catch {
    throw toError("加载练习会话失败。", "SESSION_LOAD_FAILED");
  }

  const payload = await parseResponse<BackendSession>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "加载练习会话失败。", "SESSION_LOAD_FAILED");
  }

  return toSessionSummary(payload.data);
}

export async function submitPracticeTurn(
  sessionId: string,
  input: PracticeTurnInput,
): Promise<SubmitPracticeTurnResult> {
  let response: Response;

  try {
    response = await fetch(`/api/v1/sessions/${sessionId}/reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ learner_message: input.content }),
    });
  } catch {
    throw toError("发送失败，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  const payload = await parseResponse<BackendReplyResponse>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "发送失败，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  return {
    messages: payload.data.session.messages.map(toPracticeMessage),
    feedback: toPracticeFeedback(payload.data.feedback),
  };
}