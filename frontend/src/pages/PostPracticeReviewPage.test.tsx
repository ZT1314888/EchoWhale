import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import { App } from "../App";
import * as authApi from "../services/authApi";
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

});
