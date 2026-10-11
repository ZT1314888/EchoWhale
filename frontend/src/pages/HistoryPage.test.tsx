import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows the honest empty state when the learner has no history yet", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
    });
    vi.spyOn(historyApi, "listHistorySessions").mockResolvedValue({
      items: [],
      page: { hasMore: false, nextCursor: null },
    });
    const detailSpy = vi.spyOn(historyApi, "getHistorySession");

    await renderApp(["/history"]);

    expect(await screen.findByRole("heading", { level: 2, name: /还没有历史记录/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /上传图片开始第一次练习/i })).toHaveAttribute("href", "/");
    expect(detailSpy).not.toHaveBeenCalled();
  });

  it("filters, searches and reorders the loaded entries", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
    });
    vi.spyOn(historyApi, "listHistorySessions").mockResolvedValue({
      items: [
        { ...entry("sess_coffee", "2026-04-04 15:20", "已完成 2 轮", "咖啡店柜台点单", ["coffee"]) },
        { ...entry("sess_office", "2026-05-06 09:10", "进行中", "办公室周会", ["meeting"]) },
      ],
      page: { hasMore: false, nextCursor: null },
    });
    vi.spyOn(historyApi, "getHistorySession").mockRejectedValue({ message: "not needed" });
    vi.spyOn(historyApi, "getHistorySessionMessages").mockResolvedValue({
      items: [],
      page: { hasMore: false, nextCursor: null },
    });

    await renderApp(["/history"]);

    await screen.findByRole("list", { name: /历史会话列表/i });
    const titles = () =>
      screen.getAllByRole("listitem").map((item) => item.textContent ?? "");

    expect(titles()[0]).toContain("办公室周会");

    fireEvent.click(screen.getByRole("button", { name: "最新在前" }));
    expect(titles()[0]).toContain("咖啡店柜台点单");

    fireEvent.click(screen.getByRole("button", { name: "进行中" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(titles()[0]).toContain("办公室周会");

    fireEvent.click(screen.getByRole("button", { name: "已完成" }));
    fireEvent.change(screen.getByLabelText("搜索练习历史"), { target: { value: "机场" } });
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    expect(screen.getByRole("heading", { level: 2, name: /没有匹配的记录/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("appends the next page of sessions when the learner loads more", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
    });
    const listSpy = vi
      .spyOn(historyApi, "listHistorySessions")
      .mockResolvedValueOnce({
        items: [entry("sess_1", "2026-04-04 15:20", "已完成 1 轮", "咖啡店柜台点单", ["coffee"])],
        page: { hasMore: true, nextCursor: "cursor-2" },
      })
      .mockResolvedValueOnce({
        items: [entry("sess_2", "2026-03-01 10:00", "已完成 3 轮", "办公室周会", [])],
        page: { hasMore: false, nextCursor: null },
      });
    vi.spyOn(historyApi, "getHistorySession").mockRejectedValue({ message: "not needed" });
    vi.spyOn(historyApi, "getHistorySessionMessages").mockResolvedValue({
      items: [],
      page: { hasMore: false, nextCursor: null },
    });

    await renderApp(["/history"]);

    fireEvent.click(await screen.findByRole("button", { name: /加载更多历史/i }));

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith({ limit: 20, cursor: "cursor-2" });
    });
    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /加载更多历史/i })).not.toBeInTheDocument();
  });
});

function entry(id: string, practicedAt: string, status: string, sceneTitle: string, tags: string[]) {
  return {
    id,
    practicedAt,
    status,
    sceneTitle,
    roleLabel: "店员对话",
    preview: "你已经说清楚主要需求。",
    tags,
    reviewTitle: "本轮回响",
    reviewSummary: "下一轮再补一条细节。",
  };
}
