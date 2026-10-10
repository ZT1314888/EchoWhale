import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import { App } from "../App";
import * as authApi from "../services/authApi";
import * as historyApi from "../services/historyApi";

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

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("HistoryPage", () => {
  it("renders the history route with a list and review detail panel", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });
    vi.spyOn(historyApi, "listHistorySessions").mockResolvedValue({
      items: [
        {
          id: "sess_real",
          practicedAt: "2026-04-04 15:20",
          status: "已完成 1 轮",
          sceneTitle: "咖啡店柜台点单",
          roleLabel: "店员对话",
          preview: "你已经说清楚主要需求。",
          tags: ["coffee", "menu"],
          reviewTitle: "本轮回响",
          reviewSummary: "下一轮再补一条细节。",
        },
      ],
      page: {
        hasMore: false,
        nextCursor: null,
      },
    });
    vi.spyOn(historyApi, "getHistorySession").mockResolvedValue({
      entry: {
        id: "sess_real",
        practicedAt: "2026-04-04 15:20",
        status: "已完成 1 轮",
        sceneTitle: "咖啡店柜台点单",
        roleLabel: "店员对话",
        preview: "你已经说清楚主要需求。",
        tags: ["coffee", "menu"],
        reviewTitle: "本轮回响",
        reviewSummary: "下一轮再补一条细节。",
      },
      session: {
        ...realSession,
        messages: [],
        totalMessages: realSession.messages.length,
      },
      review: realReview,
    });
    vi.spyOn(historyApi, "getHistorySessionMessages").mockResolvedValue({
      items: realSession.messages,
      page: {
        hasMore: false,
        nextCursor: null,
      },
    });

    await renderApp(["/history"]);

    expect(await screen.findByRole("heading", { level: 1, name: /练习历史/i })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: /历史会话列表/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /复盘详情/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(authApi.refresh).toHaveBeenCalledTimes(1);
      expect(historyApi.listHistorySessions).toHaveBeenCalledTimes(1);
      expect(historyApi.getHistorySession).toHaveBeenCalledWith("sess_real");
      expect(historyApi.getHistorySessionMessages).toHaveBeenCalledWith("sess_real", { limit: 20 });
    });
  });

  it("redirects anonymous history visits to the login page", async () => {
    vi.spyOn(authApi, "refresh").mockRejectedValue({
      code: "AUTH_REQUIRED",
      message: "Authentication required",
    });
    const historyListSpy = vi.spyOn(historyApi, "listHistorySessions");

    await renderApp(["/history"]);

    expect(await screen.findByRole("heading", { name: "登录账号" })).toBeInTheDocument();
    expect(historyListSpy).not.toHaveBeenCalled();
  });

});
