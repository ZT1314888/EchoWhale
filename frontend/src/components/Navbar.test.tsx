import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Navbar } from "./Navbar";
import { useAuth } from "../auth/AuthProvider";
import type { AuthState } from "../types/app";

vi.mock("../auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

const anonymous: AuthState = { status: "anonymous", user: null };
const authenticated: AuthState = {
  status: "authenticated",
  user: { userId: "user_123", email: "learner@example.com", nickname: "Echo Learner" },
};

function renderNavbar(path = "/", state: AuthState = anonymous, logout = vi.fn()) {
  vi.mocked(useAuth).mockReturnValue({
    ...state,
    login: vi.fn(),
    register: vi.fn(),
    logout,
  });

  return render(
    <MemoryRouter initialEntries={[path]}>
      <Navbar />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Navbar", () => {
  it("marks the link matching the current route as the active pill", () => {
    renderNavbar("/progress");

    const progress = screen.getByRole("link", { name: "Progress" });
    const practice = screen.getByRole("link", { name: "Practice" });

    expect(progress.className).toContain("bg-[#131311]");
    expect(practice.className).not.toContain("bg-[#131311] shadow-md");
  });

  it("treats the session route as practice and hides the center nav on auth routes", () => {
    const { unmount } = renderNavbar("/session/sess_real");
    expect(screen.getByRole("link", { name: "Practice" }).className).toContain("bg-[#131311]");
    unmount();

    renderNavbar("/login");
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
  });

  it("swaps the anonymous actions for the user chip and calls logout", () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    renderNavbar("/", authenticated, logout);

    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
    expect(screen.getByText("Echo Learner")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("opens the mobile drawer and closes it after following a link", () => {
    renderNavbar("/");

    fireEvent.click(screen.getByRole("button", { name: "导航菜单" }));

    const drawer = screen.getByRole("button", { name: "导航菜单" });
    expect(drawer).toHaveAttribute("aria-expanded", "true");

    // 抽屉里多出一组同名入口（桌面那组仍在 DOM 中）。
    expect(screen.getAllByRole("link", { name: "Library" })).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("link", { name: "Library" })[1]);
    expect(screen.getByRole("button", { name: "导航菜单" })).toHaveAttribute("aria-expanded", "false");
  });
});
