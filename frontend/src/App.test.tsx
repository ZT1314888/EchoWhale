import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import { App } from "./App";
import * as mediaApi from "./services/mediaApi";
import * as sessionApi from "./services/sessionApi";

function renderApp(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>,
  );
}

const realSession = {
  id: "sess_real",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · barista",
  openingPrompt: "开场提示：Hi there, what can I get started for you today?",
  tags: ["coffee", "menu"],
  liveHint: "先用一句短句回应，再补一条细节，会更稳。",
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

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the production home route without the prototype switcher", () => {
    renderApp();

    expect(screen.getByRole("heading", { name: /上传一个场景，马上开口练习/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /选择图片/i })).toBeInTheDocument();
    expect(screen.getByText(/试试一个示例场景/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /登录 \/ 注册/i })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /主导航/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /历史记录/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /六屏预览切换/i })).not.toBeInTheDocument();
  });

  it("navigates from upload to loading to the session route", async () => {
    vi.useFakeTimers();
    renderApp();

    fireEvent.click(screen.getByRole("button", { name: /使用示例场景/i }));
    expect(screen.getByRole("heading", { name: /正在分析你的上传内容/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /进入练习/i })).toBeDisabled();
    expect(screen.queryByRole("navigation", { name: /主导航/i })).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3200);
    });

    const enterButton = screen.getByRole("button", { name: /进入练习/i });
    expect(enterButton).toBeEnabled();

    vi.useRealTimers();
    fireEvent.click(enterButton);
    expect(await screen.findByRole("heading", { level: 2, name: /练习会话/i })).toBeInTheDocument();
    expect(screen.getByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /发送回答/i })).toBeInTheDocument();
  });

  it("uploads a real file, creates a real session, and enters the session route", async () => {
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
    vi.spyOn(sessionApi, "createPracticeSession").mockResolvedValue({ sessionId: "sess_real" });
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);

    renderApp();

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
      expect(sessionApi.createPracticeSession).toHaveBeenCalledWith("med_upload");
    });
    expect(await screen.findByRole("heading", { level: 2, name: /练习会话/i })).toBeInTheDocument();
    expect(sessionApi.getPracticeSession).toHaveBeenCalledWith("sess_real");
  });

  it("loads a real session route and submits a real reply", async () => {
    vi.spyOn(sessionApi, "getPracticeSession").mockResolvedValue(realSession);
    vi.spyOn(sessionApi, "submitPracticeTurn").mockResolvedValue({
      messages: [
        ...realSession.messages,
        {
          id: "msg_2",
          role: "learner",
          label: "你 · 本轮回答",
          content: "Could I get an iced latte, please?",
        },
        {
          id: "msg_3",
          role: "coach",
          label: "教练 · 追问",
          content: "Sure. What size would you like?",
        },
      ],
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
    });

    renderApp(["/session/sess_real"]);

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/文本补充/i), {
      target: { value: "Could I get an iced latte, please?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送回答/i }));

    await waitFor(() => {
      expect(sessionApi.submitPracticeTurn).toHaveBeenCalledWith("sess_real", {
        content: "Could I get an iced latte, please?",
      });
    });
    expect(await screen.findByText(/Sure. What size would you like/i)).toBeInTheDocument();
    expect(screen.getByText(/Your meaning is clear/i)).toBeInTheDocument();
  });

  it("shows an upload error in loading and does not enter the session route", async () => {
    vi.spyOn(mediaApi, "uploadMedia").mockRejectedValue({
      code: "UPLOAD_FAILED",
      message: "Unsupported media type: text/plain",
    });

    renderApp();

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

  it("renders the history route with a list and review detail panel", async () => {
    renderApp(["/history"]);

    expect(screen.getByRole("heading", { level: 1, name: /练习历史/i })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: /历史会话列表/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /复盘详情/i })).toBeInTheDocument();
  });

  it("navigates between login and register routes", () => {
    renderApp(["/login"]);

    expect(screen.getByRole("heading", { name: /欢迎回来/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /使用 Google 继续/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /去注册/i }));
    expect(screen.getByRole("heading", { name: /创建你的开口通道/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建账号/i })).toBeInTheDocument();
  });
});