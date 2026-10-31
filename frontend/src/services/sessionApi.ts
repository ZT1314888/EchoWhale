import type {
  AppError,
  PracticeFeedback,
  PracticeMessage,
  PracticeTurnInput,
  SessionSummary,
  SubmitPracticeTurnResult,
  VoiceBootstrapResult,
  VoiceCompleteInput,
  VoiceCompleteResult,
  ReviewSummary,
} from "../types/app";
import { apiFetch } from "./apiClient";
import { humanizeIdentifier } from "../utils/humanizeIdentifier";

type ApiResponse<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type BackendErrorData = {
  reason?: string;
  retryable?: boolean;
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
  media_id: string | null;
  scene: string;
  role: string;
  // F17：后端下发的场景展示文案；标 optional 以容忍旧后端/缓存响应，走 humanize 兜底。
  scene_title?: string;
  role_label?: string;
  opener: string;
  status: string;
  visual_anchors?: string[];
  vocab_candidates?: string[];
  labels?: string[];
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

type BackendReview = {
  session_id: string;
  title: string;
  highlight: string;
  next_try: string;
  feedback: {
    grammar: { title: string; body: string };
    more_natural: { title: string; body: string };
    useful_words: { title: string; words: string[]; body: string };
    next_step: { title: string; body: string };
  };
};

type BackendSessionStartPending = {
  status: string;
  media_id: string;
};

type BackendVoiceBootstrapResponse = {
  session_id: string;
  deepgram_access_token: string;
  expires_in: number;
  deepgram_ws_url: string;
  agent_settings: Record<string, unknown>;
  session: BackendSession;
};

type BackendVoiceCompleteResponse = {
  session: BackendSession;
  review: BackendReview;
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
    feedback: message.feedback ? toPracticeFeedback(message.feedback) : undefined,
  };
}

function toSessionSummary(session: BackendSession): SessionSummary {
  // 展示文案单一事实源（F17）：优先后端下发的 scene_title/role_label；
  // 兜底用 humanizeIdentifier（与后端 _humanize_identifier 同语义），不露原始 snake_case id。
  return {
    id: session.session_id,
    title: session.scene_title ?? `${humanizeIdentifier(session.scene)} 情景对话`,
    roleLabel: session.role_label ?? `角色 · ${humanizeIdentifier(session.role)}`,
    openingPrompt: `开场提示：${session.opener}`,
    status: session.status,
    tags: session.vocab_candidates ?? session.labels ?? [],
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

function toReviewSummary(review: BackendReview): ReviewSummary {
  return {
    sessionId: review.session_id,
    title: review.title,
    highlight: review.highlight,
    nextTry: review.next_try,
    feedback: {
      grammar: {
        title: review.feedback.grammar.title,
        body: review.feedback.grammar.body,
      },
      moreNatural: {
        title: review.feedback.more_natural.title,
        body: review.feedback.more_natural.body,
      },
      usefulWords: {
        title: review.feedback.useful_words.title,
        words: review.feedback.useful_words.words,
        body: review.feedback.useful_words.body,
      },
      nextStep: {
        title: review.feedback.next_step.title,
        body: review.feedback.next_step.body,
      },
    },
  };
}

export type SessionStartOutcome =
  | { kind: "created"; sessionId: string }
  | { kind: "analyzing"; mediaId: string };

export async function createPracticeSession(
  mediaId: string,
  signal?: AbortSignal,
): Promise<SessionStartOutcome> {
  return createSession({ media_id: mediaId }, signal);
}

export async function createSamplePracticeSession(
  sampleSceneId: "coffee" | "office" | "street",
  signal?: AbortSignal,
): Promise<SessionStartOutcome> {
  return createSession({ sample_scene_id: sampleSceneId }, signal);
}

async function createSession(
  payloadBody: { media_id: string } | { sample_scene_id: "coffee" | "office" | "street" },
  signal?: AbortSignal,
): Promise<SessionStartOutcome> {
  let response: Response;

  try {
    response = await apiFetch("/api/v1/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadBody),
      signal,
    });
  } catch (reason) {
    if ((reason as { name?: string })?.name === "AbortError") {
      throw reason;
    }
    throw toError("创建练习会话失败，请稍后重试。", "SESSION_START_FAILED");
  }

  const payload = await parseResponse<BackendSession | BackendErrorData>(response);
  if (!response.ok || !payload.data) {
    if (response.status === 422 && payload.code === 1007) {
      const errorData = payload.data as BackendErrorData | undefined;
      throw {
        code: "UNSUPPORTED_SCENE_IMAGE",
        message: "图片暂不支持这类内容，请换一张生活场景更清晰的图片。",
        reason: errorData?.reason,
      } satisfies AppError;
    }
    if (response.status >= 500 || payload.code === 1008) {
      throw {
        code: "SCENE_ANALYSIS_UNAVAILABLE",
        message: "图片分析暂时不可用，请稍后重试。",
      } satisfies AppError;
    }
    throw toError(payload.message ?? "创建练习会话失败，请稍后重试。", "SESSION_START_FAILED");
  }

  if (response.status === 202) {
    const pending = payload.data as BackendSessionStartPending | undefined;
    if (!pending || !pending.media_id) {
      throw toError("创建练习会话失败，请稍后重试。", "SESSION_START_FAILED");
    }
    return { kind: "analyzing", mediaId: pending.media_id };
  }

  return { kind: "created", sessionId: (payload.data as BackendSession).session_id };
}

export async function getPracticeSession(sessionId: string): Promise<SessionSummary> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/sessions/${sessionId}`);
  } catch {
    throw toError("加载练习会话失败。", "SESSION_LOAD_FAILED");
  }

  const payload = await parseResponse<BackendSession>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "加载练习会话失败。", "SESSION_LOAD_FAILED");
  }

  return toSessionSummary(payload.data);
}

export type PracticeTurnStreamHandlers = {
  onFeedback?: (feedback: PracticeFeedback) => void;
  onDelta?: (delta: string) => void;
};

export async function submitPracticeTurnStream(
  sessionId: string,
  input: PracticeTurnInput,
  handlers: PracticeTurnStreamHandlers = {},
  signal?: AbortSignal,
): Promise<SubmitPracticeTurnResult> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/sessions/${sessionId}/reply/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ learner_message: input.content }),
      signal,
    });
  } catch {
    throw toError("发送失败，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  if (!response.ok || !response.body) {
    const payload = await parseEnvelopeQuietly(response);
    throw toError(payload.message ?? "发送失败，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  const streamState = {
    finalData: null as BackendReplyResponse | null,
    streamError: null as { message?: string } | null,
  };

  await consumeSseResponse(response.body, (eventName, rawData) => {
    if (eventName === "feedback") {
      handlers.onFeedback?.(toPracticeFeedback(rawData as BackendReplyFeedback));
      return;
    }
    if (eventName === "delta") {
      const delta = (rawData as { text?: string }).text ?? "";
      if (delta) handlers.onDelta?.(delta);
      return;
    }
    if (eventName === "session") {
      streamState.finalData = rawData as BackendReplyResponse;
      return;
    }
    if (eventName === "error") {
      streamState.streamError = rawData as { message?: string };
    }
  });

  if (streamState.streamError) {
    throw toError(streamState.streamError.message ?? "发送失败，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  const finalData = streamState.finalData;
  if (finalData === null) {
    throw toError("回复流提前结束，请稍后再试。", "TURN_SUBMIT_FAILED");
  }

  return {
    messages: finalData.session.messages.map(toPracticeMessage),
    feedback: toPracticeFeedback(finalData.feedback),
  };
}

async function parseEnvelopeQuietly(response: Response): Promise<ApiResponse<unknown>> {
  try {
    return (await response.json()) as ApiResponse<unknown>;
  } catch {
    return {};
  }
}

async function consumeSseResponse(
  body: ReadableStream<Uint8Array>,
  onEvent: (eventName: string, rawData: unknown) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatchFrame = (frame: string) => {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const rawLine of frame.split("\n")) {
      const line = rawLine.replace(/\r$/, "");
      if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trim());
      }
    }
    if (!dataLines.length) return;
    try {
      onEvent(eventName, JSON.parse(dataLines.join("\n")) as unknown);
    } catch {
      // 与后端解析口径一致：无法解析的帧静默忽略。
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        dispatchFrame(buffer.slice(0, separator));
        buffer = buffer.slice(separator + 2);
        separator = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatchFrame(buffer.trimEnd());
  } finally {
    // 正常结束、中途失败或 AbortSignal 触发都必须收回读取器；
    // 流已关闭/已出错时 cancel 自身会拒绝，静默处理。
    await reader.cancel().catch(() => {
      // no-op
    });
  }
}

export async function bootstrapVoiceSession(sessionId: string): Promise<VoiceBootstrapResult> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/sessions/${sessionId}/voice/bootstrap`, {
      method: "POST",
    });
  } catch {
    throw toError("语音会话启动失败，请稍后再试。", "VOICE_BOOTSTRAP_FAILED");
  }

  const payload = await parseResponse<BackendVoiceBootstrapResponse>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "语音会话启动失败，请稍后再试。", "VOICE_BOOTSTRAP_FAILED");
  }

  return {
    sessionId: payload.data.session_id,
    deepgramAccessToken: payload.data.deepgram_access_token,
    deepgramWsUrl: payload.data.deepgram_ws_url,
    expiresIn: payload.data.expires_in,
    agentSettings: payload.data.agent_settings,
    session: toSessionSummary(payload.data.session),
  };
}

export async function completeVoiceSession(
  sessionId: string,
  input: VoiceCompleteInput,
): Promise<VoiceCompleteResult> {
  let response: Response;

  try {
    response = await apiFetch(`/api/v1/sessions/${sessionId}/voice/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation: input.conversation,
        termination_reason: input.terminationReason,
        client_diagnostics: input.clientDiagnostics ?? {},
      }),
    });
  } catch {
    throw toError("语音会话结束失败，请稍后再试。", "VOICE_COMPLETE_FAILED");
  }

  const payload = await parseResponse<BackendVoiceCompleteResponse>(response);
  if (!response.ok || !payload.data) {
    throw toError(payload.message ?? "语音会话结束失败，请稍后再试。", "VOICE_COMPLETE_FAILED");
  }

  return {
    session: toSessionSummary(payload.data.session),
    review: toReviewSummary(payload.data.review),
  };
}
