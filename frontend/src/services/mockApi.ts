import { baseSession, defaultFeedback, historyDetails, historyEntries, sampleScenes } from "../data/mockApp";
import type {
  AppError,
  AuthCredentials,
  AuthResult,
  HistoryDetail,
  HistoryEntry,
  PracticeTurnInput,
  RegisterPayload,
  ReviewSummary,
  SessionSummary,
  SubmitPracticeTurnResult,
  UploadDraft,
} from "../types/app";

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function wait<T>(value: T): Promise<T> {
  return Promise.resolve(clone(value));
}

function toError(code: string, message: string): AppError {
  return { code, message };
}

const sessionStore = new Map<string, SessionSummary>(
  Object.values(historyDetails).map((detail) => [detail.session.id, clone(detail.session)]),
);

function ensureSession(sessionId: string): SessionSummary {
  const session = sessionStore.get(sessionId);

  if (!session) {
    throw toError("SESSION_NOT_FOUND", "没有找到这轮练习。");
  }

  return session;
}

export async function createPracticeSession(draft: UploadDraft): Promise<{ sessionId: string }> {
  if (draft.source === "sample" && draft.sampleSceneId) {
    const matched = sampleScenes.find((scene) => scene.id === draft.sampleSceneId);

    if (matched?.id === "coffee") {
      return wait({ sessionId: "session-coffee" });
    }
  }

  return wait({ sessionId: "session-coffee" });
}

export async function getPracticeSession(sessionId: string): Promise<SessionSummary> {
  return wait(ensureSession(sessionId));
}

export async function submitPracticeTurn(
  sessionId: string,
  input: PracticeTurnInput,
): Promise<SubmitPracticeTurnResult> {
  const content = input.content.trim();

  if (!content) {
    throw toError("TURN_EMPTY", "先写一句英文回答再发送。");
  }

  const session = clone(ensureSession(sessionId));
  const learnerMessage = {
    id: `${sessionId}-learner-${session.messages.length + 1}`,
    role: "learner" as const,
    label: "你 · 本轮回答",
    content,
  };
  const coachMessage = {
    id: `${sessionId}-coach-${session.messages.length + 2}`,
    role: "coach" as const,
    label: "教练 · 追问",
    content: "Nice. Add one more detail in a second sentence so the reply sounds more complete.",
  };

  session.messages = [...session.messages, learnerMessage, coachMessage];
  sessionStore.set(sessionId, session);

  return wait({
    messages: session.messages,
    feedback: defaultFeedback,
  });
}

export async function getPracticeReview(sessionId: string): Promise<ReviewSummary> {
  const detail = historyDetails[sessionId];

  if (!detail) {
    throw toError("REVIEW_NOT_FOUND", "还没有可查看的练后反馈。");
  }

  return wait(detail.review);
}

export async function listHistorySessions(): Promise<HistoryEntry[]> {
  return wait(historyEntries);
}

export async function getHistorySession(sessionId: string): Promise<HistoryDetail> {
  const detail = historyDetails[sessionId];

  if (!detail) {
    throw toError("HISTORY_NOT_FOUND", "没有找到这条历史记录。");
  }

  return wait(detail);
}

export async function login(credentials: AuthCredentials): Promise<AuthResult> {
  if (!credentials.email.trim()) {
    throw toError("AUTH_INVALID", "请输入邮箱地址。");
  }

  if (!credentials.password.trim()) {
    throw toError("AUTH_INVALID", "请输入密码。");
  }

  return wait({ userName: "Echo Learner" });
}

export async function register(payload: RegisterPayload): Promise<AuthResult> {
  if (!payload.nickname.trim()) {
    throw toError("AUTH_INVALID", "请输入昵称。");
  }

  await login(payload);
  return wait({ userName: payload.nickname.trim() });
}
