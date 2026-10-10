import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

vi.mock("./hooks/useDeepgramVoiceAgent", () => ({
  useDeepgramVoiceAgent: vi.fn(() => ({
    error: "",
    isConnected: false,
    isListening: false,
    isThinking: false,
    isSpeaking: false,
    transcript: [],
    startSession: vi.fn().mockResolvedValue(undefined),
    endSession: vi.fn().mockResolvedValue({
      conversation: [],
      terminationReason: "user_ended",
    }),
  })),
}));

import { App } from "./App";
import { useDeepgramVoiceAgent } from "./hooks/useDeepgramVoiceAgent";
import * as authApi from "./services/authApi";
import * as mediaApi from "./services/mediaApi";
import * as reviewApi from "./services/reviewApi";
import * as sessionApi from "./services/sessionApi";

type MockSpeechResult = {
  transcript: string;
  isFinal: boolean;
};

class MockSpeechRecognition {
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn(() => {
    this.onend?.();
  });
  abort = vi.fn();

  emitResult(...results: MockSpeechResult[]) {
    const mapped = results.map((result) =>
      Object.assign([{ transcript: result.transcript }], {
        isFinal: result.isFinal,
        length: 1,
      }),
    );

    this.onresult?.({
      resultIndex: 0,
      results: Object.assign(mapped, { length: mapped.length }),
    });
  }

  emitError(error: string) {
    this.onerror?.({ error });
  }
}

function installSpeechRecognitionMock() {
  const instances: MockSpeechRecognition[] = [];
  const recognitionFactory = vi.fn(() => {
    const instance = new MockSpeechRecognition();
    instances.push(instance);
    return instance;
  });

  Object.defineProperty(window, "SpeechRecognition", {
    configurable: true,
    writable: true,
    value: recognitionFactory,
  });
  Object.defineProperty(window, "webkitSpeechRecognition", {
    configurable: true,
    writable: true,
    value: recognitionFactory,
  });

  return {
    recognitionFactory,
    getLastInstance() {
      return instances.at(-1);
    },
  };
}

async function renderApp(initialEntries: string[] = ["/"]) {
  if (!vi.isMockFunction(authApi.refresh)) {
    vi.spyOn(authApi, "refresh").mockRejectedValue({
      code: "AUTH_REQUIRED",
      message: "Authentication required",
    });
  }

  let rendered: ReturnType<typeof render> | undefined;

  await act(async () => {
    rendered = render(
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>,
    );
    await Promise.resolve();
  });

  return rendered!;
}

const realSession = {
  id: "sess_real",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · barista",
  openingPrompt: "开场提示：Hi there, what can I get started for you today?",
  tags: ["coffee", "menu"],
  voiceTitle: "点一下，用声音回答",
  voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
  messages: [
    {
      id: "msg_1",
      role: "coach" as const,
      label: "教练 · 追问",
      content: "Hi there, what can I get started for you today?",
    },
  ],
};

const realReview = {
  sessionId: "sess_real",
  title: "本轮回响",
  highlight: "你已经说清楚主要需求。",
  nextTry: "下一轮再补一条细节。",
  feedback: {
    grammar: { title: "Grammar", body: "Your meaning is clear." },
    moreNatural: { title: "More Natural", body: "Could I get an iced latte, please?" },
    usefulWords: {
      title: "Useful Words",
      words: ["latte", "size", "iced"],
      body: "把这些词带进下一轮回答，会更自然。",
    },
    nextStep: { title: "Next Step", body: "下一轮试着在一句主回应后再补一句细节。" },
  },
};

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  delete (window as typeof window & { SpeechRecognition?: unknown }).SpeechRecognition;
  delete (window as typeof window & { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
});

describe("App", () => {
  it("renders the production home route without the prototype switcher", async () => {
    await renderApp();

    expect(screen.getByRole("heading", { name: /上传一个场景，马上开口练习/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /选择图片/i })).toBeInTheDocument();
    expect(screen.getByText(/试试一个示例场景/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "咖啡店柜台与点单场景" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "办公室内的工作交流场景" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "街头出行与问路场景" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /登录 \/ 注册/i })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /主导航/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /历史记录/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /六屏预览切换/i })).not.toBeInTheDocument();
  });

  it("navigates from upload to loading to the session route", async () => {
    vi.useFakeTimers();
    installSpeechRecognitionMock();
    vi.spyOn(sessionApi, "createSamplePracticeSession").mockResolvedValue({
      kind: "created",
      sessionId: "sess_real",
    });
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);
    await renderApp();

    fireEvent.click(screen.getByRole("button", { name: /使用示例场景/i }));
    expect(screen.getByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /进入练习/i })).toBeDisabled();
    expect(screen.queryByRole("navigation", { name: /主导航/i })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3200);
    });

    const enterButton = screen.getByRole("button", { name: /进入练习/i });
    expect(enterButton).toBeEnabled();

    vi.useRealTimers();
    fireEvent.click(enterButton);
    expect(await screen.findByRole("button", { name: /start voice practice/i })).toBeInTheDocument();
    expect(sessionApi.createSamplePracticeSession).toHaveBeenCalledWith(
      "coffee",
      expect.anything(),
    );
    expect(sessionApi.getPracticeSession).toHaveBeenCalledWith("sess_real");
    expect(screen.getByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /发送/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/用文字继续练习/i)).toBeInTheDocument();
  });

  it("uploads a real file, creates a real session, and enters the session route", async () => {
    installSpeechRecognitionMock();
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_upload",
      filename: "lunch.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/2026/04/01/med_upload-lunch.png",
      previewUrl: "https://signed.test/media/demo-user/2026/04/01/med_upload-lunch.png?signature=demo",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({ kind: "created", sessionId: "sess_real" });
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "lunch.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(mediaApi.uploadMedia).toHaveBeenCalledWith(file);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });

    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    await waitFor(() => {
      expect(sessionApi.createPracticeSession).toHaveBeenCalledWith(
      "med_upload",
      expect.anything(),
    );
    });
    expect(await screen.findByRole("button", { name: /start voice practice/i })).toBeInTheDocument();
    expect(sessionApi.getPracticeSession).toHaveBeenCalledWith("sess_real");
  });

  it("starts a voice-first session and ends by completing the Deepgram voice session", async () => {
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);
    vi.spyOn(sessionApi, "bootstrapVoiceSession").mockResolvedValue({
      sessionId: "sess_real",
      deepgramAccessToken: "dg-token",
      deepgramWsUrl: "wss://api.deepgram.com/v1/agent/converse",
      expiresIn: 600,
      agentSettings: { type: "Settings" },
      session: realSession,
    });
    vi.spyOn(sessionApi, "completeVoiceSession").mockResolvedValue({
      session: {
        ...realSession,
        messages: [
          ...realSession.messages,
          {
            id: "msg_2",
            role: "learner",
            label: "你 · 本轮回答",
            content: "Could I get an iced latte, please?",
          },
        ],
      },
      review: realReview,
    });
    vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);
    vi.mocked(useDeepgramVoiceAgent).mockReturnValue({
      error: "",
      isConnected: false,
      isListening: false,
      isThinking: false,
      isSpeaking: false,
      transcript: [
        { role: "assistant", content: "Hi there, what can I get started for you today?" },
        { role: "user", content: "Could I get an iced latte, please?" },
      ],
      startSession: vi.fn().mockResolvedValue(undefined),
      endSession: vi.fn().mockResolvedValue({
        conversation: [
          { role: "assistant", content: "Hi there, what can I get started for you today?" },
          { role: "user", content: "Could I get an iced latte, please?" },
        ],
        terminationReason: "user_ended",
      }),
    });

    await renderApp(["/session/sess_real"]);

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start voice practice/i }));

    expect(await screen.findByText(/Could I get an iced latte, please/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /end voice practice/i }));

    await waitFor(() => {
      expect(sessionApi.bootstrapVoiceSession).toHaveBeenCalledWith("sess_real");
      expect(sessionApi.completeVoiceSession).toHaveBeenCalledWith("sess_real", {
        conversation: [
          { role: "assistant", content: "Hi there, what can I get started for you today?" },
          { role: "user", content: "Could I get an iced latte, please?" },
        ],
        terminationReason: "user_ended",
      });
    });
    expect(await screen.findByRole("heading", { level: 2, name: /练后反馈/i })).toBeInTheDocument();
  });

  it("shows an upload error in loading and does not enter the session route", async () => {
    vi.spyOn(mediaApi, "uploadMedia").mockRejectedValue({
      code: "UPLOAD_FAILED",
      message: "Unsupported media type: text/plain",
    });

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "bad.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    expect(await screen.findByText(/Unsupported media type: text\/plain/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /重试上传/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { level: 2, name: /练习会话/i })).not.toBeInTheDocument();
  });

  it("shows an unsupported-image message when session creation is rejected", async () => {
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_black",
      filename: "black.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/2026/04/01/med_black-black.png",
      previewUrl: "https://signed.test/media/demo-user/2026/04/01/med_black-black.png?signature=demo",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    vi.spyOn(sessionApi, "createPracticeSession").mockRejectedValue({
      code: "UNSUPPORTED_SCENE_IMAGE",
      message: "图片暂不支持这类内容，请换一张生活场景更清晰的图片。",
      reason: "image_too_uniform",
    });

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "black.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });

    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    expect(
      await screen.findByText(/图片暂不支持这类内容，请换一张生活场景更清晰的图片。/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /返回首页重新选择/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /练习会话/i })).not.toBeInTheDocument();
  });

  it("shows a retryable analysis-unavailable message when session creation fails temporarily", async () => {
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_retry",
      filename: "classroom.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/2026/04/01/med_retry-classroom.png",
      previewUrl: "https://signed.test/media/demo-user/2026/04/01/med_retry-classroom.png?signature=demo",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    vi.spyOn(sessionApi, "createPracticeSession").mockRejectedValue({
      code: "SCENE_ANALYSIS_UNAVAILABLE",
      message: "图片分析暂时不可用，请稍后重试。",
    });

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "classroom.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });

    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    expect(await screen.findByText("图片分析暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重试创建练习/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /练习会话/i })).not.toBeInTheDocument();
  });

  it("redirects successful login to the home page when there is no next query", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("heading", { name: /上传一个场景，马上开口练习/i })).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent(/登录成功/i);
    expect(screen.getByText(/已成功登录，欢迎回来/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /关闭登录成功提示/i }));
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("shows a localized error when login credentials are invalid", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "邮箱/密码错误",
    });

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "wrong-pass" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("邮箱/密码错误")).toBeInTheDocument();
    expect(screen.queryByText("Invalid email or password")).not.toBeInTheDocument();
  });

  it("shows a localized login validation error when the api rejects the email address", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "邮箱格式错误",
    });

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("邮箱格式错误")).toBeInTheDocument();
    expect(screen.queryByText("Invalid email format")).not.toBeInTheDocument();
    expect(screen.queryByText("Validation error")).not.toBeInTheDocument();
  });

  it("skips login when the email address is malformed", async () => {
    const loginSpy = vi.spyOn(authApi, "login");

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "not-an-email" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(loginSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("请输入邮箱地址")).not.toBeInTheDocument();
  });

  it("shows a localized login validation error for password rules", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "密码至少 8 位且需包含字母和数字",
    });

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("密码至少 8 位且需包含字母和数字")).toBeInTheDocument();
    expect(screen.queryByText("Password must include letters and numbers")).not.toBeInTheDocument();
    expect(screen.queryByText("Password must be at least 8 characters")).not.toBeInTheDocument();
  });

  it("shows a localized login error for pending verification", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "请先完成邮箱验证后再登录",
    });

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("请先完成邮箱验证后再登录")).toBeInTheDocument();
    expect(screen.queryByText("Please verify your email before logging in")).not.toBeInTheDocument();
  });

  it("shows a localized error and skips login when email is blank", async () => {
    const loginSpy = vi.spyOn(authApi, "login");

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("请输入邮箱地址")).toBeInTheDocument();
    expect(loginSpy).not.toHaveBeenCalled();
  });

  it("shows a localized error and skips login when password is blank", async () => {
    const loginSpy = vi.spyOn(authApi, "login");

    await renderApp(["/login"]);

    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("请输入密码")).toBeInTheDocument();
    expect(loginSpy).not.toHaveBeenCalled();
  });

  it("redirects successful registration to the verify-email instructions page", async () => {
    vi.spyOn(authApi, "register").mockResolvedValue(undefined);

    await renderApp(["/register?next=%2Fhistory"]);

    expect(screen.getByLabelText("昵称")).toHaveValue("");
    expect(screen.getByLabelText("邮箱地址")).toHaveValue("");
    expect(screen.getByLabelText("密码")).toHaveValue("");
    expect(screen.getByLabelText("确认密码")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByRole("heading", { name: /查收你的验证码/i })).toBeInTheDocument();
    expect(screen.getByText(/learner@example.com/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "创建账号" })).not.toBeInTheDocument();
  });

  it("shows a localized registration error when the email already exists", async () => {
    vi.spyOn(authApi, "register").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "该邮箱已被注册",
    });

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("该邮箱已被注册")).toBeInTheDocument();
    expect(screen.queryByText("Email already registered")).not.toBeInTheDocument();
  });

  it("shows a localized registration validation error when the api rejects the email address", async () => {
    vi.spyOn(authApi, "register").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "邮箱格式错误",
    });

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("邮箱格式错误")).toBeInTheDocument();
    expect(screen.queryByText("Invalid email format")).not.toBeInTheDocument();
    expect(screen.queryByText("Validation error")).not.toBeInTheDocument();
  });

  it("skips registration when the email address is malformed", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "not-an-email" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(registerSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("请输入邮箱地址")).not.toBeInTheDocument();
  });

  it("shows a localized registration validation error for password rules", async () => {
    vi.spyOn(authApi, "register").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "密码至少 8 位且需包含字母和数字",
    });

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "password" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("密码至少 8 位且需包含字母和数字")).toBeInTheDocument();
    expect(screen.queryByText("Password must include letters and numbers")).not.toBeInTheDocument();
    expect(screen.queryByText("Password must be at least 8 characters")).not.toBeInTheDocument();
  });

  it("shows a localized error and skips registration when nickname is blank", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("请输入昵称")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("shows a localized error and skips registration when email is blank", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("请输入邮箱地址")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("shows a localized error and skips registration when password is blank", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("请输入密码")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("shows a localized error and skips registration when the password is too short", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "abc12" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "abc12" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("密码长度至少为 6 个字符")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("shows a localized error and skips registration when the password confirmation differs", async () => {
    const registerSpy = vi.spyOn(authApi, "register");

    await renderApp(["/register"]);

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "Echo Learner" },
    });
    fireEvent.change(screen.getByLabelText("邮箱地址"), {
      target: { value: "learner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "secret456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建账号/i }));

    expect(await screen.findByText("两次输入的密码不一致")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("shows an authenticated nickname menu and restores anonymous actions after logout", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });
    vi.spyOn(authApi, "logout").mockResolvedValue(undefined);

    await renderApp(["/"]);

    const nicknameTrigger = await screen.findByRole("button", { name: /echo learner/i });
    const menuContainer = nicknameTrigger.closest(".user-menu");

    expect(menuContainer).not.toBeNull();
    expect(screen.queryByRole("link", { name: /登录 \/ 注册/i })).not.toBeInTheDocument();

    fireEvent.mouseEnter(menuContainer!);
    const logoutButton = await screen.findByRole("menuitem", { name: /退出登录/i });

    fireEvent.mouseLeave(menuContainer!);
    expect(screen.getByRole("menuitem", { name: /退出登录/i })).toBeInTheDocument();
    fireEvent.click(logoutButton);

    await waitFor(() => {
      expect(authApi.logout).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByRole("link", { name: /登录 \/ 注册/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /echo learner/i })).not.toBeInTheDocument();
  });

  it("navigates between login and register routes", async () => {
    await renderApp(["/login"]);

    expect(screen.getByRole("heading", { name: "登录账号" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /忘记密码/i }));
    expect(screen.getByRole("heading", { name: "忘记密码" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /返回登录/i }));
    expect(await screen.findByRole("heading", { name: "登录账号" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /创建新账号/i }));
    expect(screen.getByRole("heading", { name: "创建账号" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建账号/i })).toBeInTheDocument();
  });

  it("submits email verification codes from the verification route", async () => {
    vi.spyOn(authApi, "verifyEmail").mockResolvedValue(undefined);

    await renderApp(["/verify-email?email=learner%40example.com"]);

    expect(screen.getByText(/learner@example.com/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/验证码/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /完成验证/i }));

    expect(await screen.findByRole("heading", { name: /邮箱验证完成/i })).toBeInTheDocument();
    expect(authApi.verifyEmail).toHaveBeenCalledWith({
      email: "learner@example.com",
      code: "123456",
    });
  });

  it("keeps invalid reset links on the reset page and shows a retry action", async () => {
    vi.spyOn(authApi, "resetPassword").mockRejectedValue({
      code: "AUTH_API_FAILED",
      message: "重置链接已失效或已过期，请重新申请。",
    });

    await renderApp(["/reset-password?token=expired-token"]);

    fireEvent.change(screen.getByLabelText(/新密码/i), {
      target: { value: "renew1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /确认重置密码/i }));

    expect(await screen.findByText("重置链接已失效或已过期，请重新申请。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重新申请重置邮件/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /重置密码/i })).toBeInTheDocument();
  });

  it("shows success feedback and redirects to login after a successful password reset", async () => {
    vi.useFakeTimers();
    vi.spyOn(authApi, "resetPassword").mockResolvedValue(undefined);

    await renderApp(["/reset-password?token=valid-token"]);

    fireEvent.change(screen.getByLabelText(/新密码/i), {
      target: { value: "renew1234" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /确认重置密码/i }));
      await Promise.resolve();
    });

    expect(screen.getByText(/密码已更新/i)).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
      await Promise.resolve();
    });
    vi.useRealTimers();
    expect(screen.getByRole("heading", { name: "登录账号" })).toBeInTheDocument();
  });

  it("waits out async scene analysis and enters the session when the retry succeeds", async () => {
    installSpeechRecognitionMock();
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_async",
      filename: "counter.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/med_async-counter.png",
      previewUrl: "https://signed.test/med_async",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    let releaseSession!: (value: { kind: "created"; sessionId: string }) => void;
    const pendingSession = new Promise<{ kind: "created"; sessionId: string }>((resolve) => {
      releaseSession = resolve;
    });
    const createSpy = vi
      .spyOn(sessionApi, "createPracticeSession")
      .mockResolvedValueOnce({ kind: "analyzing", mediaId: "med_async" })
      .mockReturnValueOnce(pendingSession);
    vi.spyOn(mediaApi, "waitForSceneAnalysis").mockResolvedValue(undefined);
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "counter.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });

    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    expect(await screen.findByText(/场景分析排队中/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /正在分析场景/i })).toBeInTheDocument();

    act(() => {
      releaseSession({ kind: "created", sessionId: "sess_async" });
    });
    expect(await screen.findByRole("button", { name: /start voice practice/i })).toBeInTheDocument();
    expect(createSpy).toHaveBeenCalledTimes(2);
    expect(mediaApi.waitForSceneAnalysis).toHaveBeenCalledWith(
      "med_async",
      expect.objectContaining({
        signal: expect.anything(),
        onStatus: expect.any(Function),
      }),
    );
    expect(sessionApi.getPracticeSession).toHaveBeenCalledWith("sess_async");
  });

  it("offers retry and change-image actions when async scene analysis fails", async () => {
    installSpeechRecognitionMock();
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_fail",
      filename: "counter.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/med_fail-counter.png",
      previewUrl: "https://signed.test/med_fail",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({
      kind: "analyzing",
      mediaId: "med_fail",
    });
    vi.spyOn(mediaApi, "waitForSceneAnalysis").mockRejectedValue({
      code: "SCENE_ANALYSIS_FAILED",
      message: "图片场景分析失败，请重试或换一张图片。",
    });

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "counter.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });

    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    expect(await screen.findByText("图片场景分析失败，请重试或换一张图片。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重试创建练习/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /换一张图片/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /练习暂时不可用/i })).not.toBeInTheDocument();
  });

  it("lets the learner cancel the analysis wait and return home", async () => {
    installSpeechRecognitionMock();
    vi.spyOn(mediaApi, "uploadMedia").mockResolvedValue({
      mediaId: "med_cancel",
      filename: "counter.png",
      contentType: "image/png",
      fileSize: 5,
      storageKey: "media/demo-user/med_cancel-counter.png",
      previewUrl: "https://signed.test/med_cancel",
      previewUrlExpiresAt: "2026-04-02T12:00:00Z",
      uploadStatus: "uploaded",
    });
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({
      kind: "analyzing",
      mediaId: "med_cancel",
    });
    vi.spyOn(mediaApi, "waitForSceneAnalysis").mockImplementation(
      () => new Promise(() => {}),
    );

    await renderApp();

    const input = screen.getByLabelText(/点击上传，或把图片拖到这里/i, {
      selector: "input",
    });
    const file = new File(["hello"], "counter.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /进入练习/i })).toBeEnabled();
    }, { timeout: 4000 });
    fireEvent.click(screen.getByRole("button", { name: /进入练习/i }));

    expect(await screen.findByText(/场景分析排队中/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /取消等待/i }));

    expect(
      await screen.findByRole("heading", { name: /上传一个场景，马上开口练习/i }),
    ).toBeInTheDocument();
  });

});
