import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import { App } from "../App";
import * as authApi from "../services/authApi";
import * as historyApi from "../services/historyApi";
import * as reviewApi from "../services/reviewApi";

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

describe("PostPracticeReviewPage", () => {
  it("loads a real review route for real session ids", async () => {
    vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);

    await renderApp(["/session/sess_real/review"]);

    expect(await screen.findByRole("heading", { level: 2, name: /练后反馈/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(reviewApi.getPracticeReview).toHaveBeenCalledWith("sess_real");
    });
    expect(screen.getByText(/你已经说清楚主要需求/i)).toBeInTheDocument();
  });

  it("keeps the review empty state free of leaked english errors", async () => {
    vi.spyOn(reviewApi, "getPracticeReview").mockRejectedValue({
      code: "REVIEW_API_FAILED",
      message: "Session review sess_552fc05a3fac not found",
    });

    await renderApp(["/session/sess_real/review"]);

    expect(await screen.findByRole("heading", { name: /练后反馈还没准备好/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /返回练习/i })).toHaveAttribute("href", "/session/sess_real");
    expect(screen.queryByText("Session review sess_552fc05a3fac not found")).not.toBeInTheDocument();
    expect(screen.queryByText(/暂时无法读取练后反馈/i)).not.toBeInTheDocument();
  });

  it("loads review data through the real review api even when the session id does not use sess_ prefix", async () => {
    const reviewSpy = vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);

    await renderApp(["/session/session-coffee/review"]);

    expect(await screen.findByRole("heading", { level: 2, name: /练后反馈/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(reviewSpy).toHaveBeenCalledWith("session-coffee");
    });
  });

  it("shows the backend messages in the transcript tab and pages older ones in", async () => {
    vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);
    const messagesSpy = vi
      .spyOn(historyApi, "getHistorySessionMessages")
      .mockResolvedValueOnce({
        items: [
          { id: "msg_2", role: "learner", label: "你 · 本轮回答", content: "Could I get an iced latte, please?" },
        ],
        page: { hasMore: true, nextCursor: "cursor-1" },
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: "msg_1",
            role: "coach",
            label: "教练 · 追问",
            content: "Hi there, what can I get started for you today?",
          },
        ],
        page: { hasMore: false, nextCursor: null },
      });

    await renderApp(["/session/sess_real/review"]);

    await screen.findByRole("heading", { level: 2, name: /练后反馈/i });
    fireEvent.click(screen.getByRole("tab", { name: /逐字稿/i }));

    expect(await screen.findByText("Could I get an iced latte, please?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /加载更早消息/i }));

    await waitFor(() => {
      expect(messagesSpy).toHaveBeenLastCalledWith("sess_real", { limit: 20, cursor: "cursor-1" });
    });
    expect(
      await screen.findByText("Hi there, what can I get started for you today?"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /加载更早消息/i })).not.toBeInTheDocument();
  });

  it("keeps the transcript empty state honest when there are no persisted messages", async () => {
    vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);
    vi.spyOn(historyApi, "getHistorySessionMessages").mockResolvedValue({
      items: [],
      page: { hasMore: false, nextCursor: null },
    });

    await renderApp(["/session/sess_real/review"]);

    await screen.findByRole("heading", { level: 2, name: /练后反馈/i });
    fireEvent.click(screen.getByRole("tab", { name: /逐字稿/i }));

    expect(await screen.findByText(/还没有逐字稿/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /加载更早消息/i })).not.toBeInTheDocument();
  });

  it("renders every real feedback metric plus the empty score placeholders", async () => {
    vi.spyOn(reviewApi, "getPracticeReview").mockResolvedValue(realReview);
    vi.spyOn(historyApi, "getHistorySessionMessages").mockResolvedValue({
      items: [],
      page: { hasMore: false, nextCursor: null },
    });

    await renderApp(["/session/sess_real/review"]);

    await screen.findByRole("heading", { level: 2, name: /练后反馈/i });

    expect(screen.getByText("Your meaning is clear.")).toBeInTheDocument();
    expect(screen.getByText("Could I get an iced latte, please?")).toBeInTheDocument();
    expect(screen.getByText("下一轮试着在一句主回应后再补一句细节。")).toBeInTheDocument();
    expect(screen.getByText("latte").closest("div")).not.toBeNull();
    // 后端没有分数/词数/时长，界面上必须是占位符而不是编造数字。
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
  });

});
