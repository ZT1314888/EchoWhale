import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import { App } from "../App";
import * as authApi from "../services/authApi";
import * as learnerApi from "../services/learnerApi";


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

describe("ProgressPage", () => {
  it("renders the progress empty state for authenticated visits", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });
    const profileSpy = vi.spyOn(learnerApi, "getLearnerProfile").mockResolvedValue({
      cefrEstimate: null,
      errorTypes: [],
      scenes: [],
      practicedTurnCount: 0,
      updatedAt: null,
    });

    await renderApp(["/progress"]);

    expect(await screen.findByRole("heading", { level: 1, name: /我的进度/i })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /上传图片开始第一次练习/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(profileSpy).toHaveBeenCalledTimes(1);
    });
  });

  it("renders the progress overview cards when the learner has practiced turns", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: {
        userId: "user_123",
        email: "learner@example.com",
        nickname: "Echo Learner",
      },
    });
    vi.spyOn(learnerApi, "getLearnerProfile").mockResolvedValue({
      cefrEstimate: "B1",
      errorTypes: [{ category: "tense", label: "时态", count: 12 }],
      scenes: [{ sceneTitle: "咖啡店柜台点单", count: 8 }],
      practicedTurnCount: 23,
      updatedAt: "2026-10-06 15:20",
    });

    await renderApp(["/progress"]);

    expect(await screen.findByRole("heading", { level: 1, name: /我的进度/i })).toBeInTheDocument();
    expect(await screen.findByText("进阶（B1）")).toBeInTheDocument();
    expect(screen.getByText("时态")).toBeInTheDocument();
    expect(screen.getByText("咖啡店柜台点单")).toBeInTheDocument();
    expect(screen.getByText("23 轮")).toBeInTheDocument();
    expect(screen.getByText("最近更新：2026-10-06 15:20")).toBeInTheDocument();
  });

  it("redirects anonymous progress visits to the login page without fetching the profile", async () => {
    vi.spyOn(authApi, "refresh").mockRejectedValue({
      code: "AUTH_REQUIRED",
      message: "Authentication required",
    });
    const profileSpy = vi.spyOn(learnerApi, "getLearnerProfile");

    await renderApp(["/progress"]);

    expect(await screen.findByRole("heading", { name: "登录账号" })).toBeInTheDocument();
    expect(profileSpy).not.toHaveBeenCalled();
  });

  it("keeps the level segments dark and the score placeholders empty when the backend has no estimate", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
    });
    vi.spyOn(learnerApi, "getLearnerProfile").mockResolvedValue({
      cefrEstimate: null,
      errorTypes: [],
      scenes: [],
      practicedTurnCount: 4,
      updatedAt: null,
    });

    await renderApp(["/progress"]);

    expect(await screen.findByText("暂无水平估计，继续练习后会自动生成")).toBeInTheDocument();
    expect(screen.getByText("0 / 6")).toBeInTheDocument();
    expect(screen.getByText("4 轮")).toBeInTheDocument();
    // 无估计时不点亮任何一段，且没有「最近更新」这类空字段。
    expect(screen.queryByText(/最近更新/)).not.toBeInTheDocument();
    expect(screen.queryByText("0 / 6 已解锁")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 6 已解锁")).toBeInTheDocument();
  });

  it("surfaces a load failure instead of an empty state", async () => {
    vi.spyOn(authApi, "refresh").mockResolvedValue({
      accessToken: "access-token-1",
      user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
    });
    vi.spyOn(learnerApi, "getLearnerProfile").mockRejectedValue({ message: "学习进度加载失败。" });

    await renderApp(["/progress"]);

    expect(await screen.findByText("学习进度加载失败。")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /还没有练习数据/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /成就/i })).not.toBeInTheDocument();
  });

});
