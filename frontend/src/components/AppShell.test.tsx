import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

import { useAuth } from "../auth/AuthProvider";

vi.mock("../auth/AuthProvider", () => ({
  useAuth: vi.fn(() => ({
    status: "anonymous",
    user: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  })),
}));

function renderShell(path: string) {
  vi.mocked(useAuth).mockReturnValue({
    status: "anonymous",
    user: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  });

  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<p>home</p>} />
          <Route path="/session/:sessionId" element={<p>session</p>} />
          <Route path="/session/:sessionId/review" element={<p>review</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AppShell", () => {
  it("renders the navbar, the route outlet and the footer", () => {
    renderShell("/");

    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByText("home")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "页脚导航" })).toBeInTheDocument();
  });

  it("suppresses the footer on the immersive session route only", () => {
    const { unmount } = renderShell("/session/sess_real");
    expect(screen.getByText("session")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "页脚导航" })).not.toBeInTheDocument();
    unmount();

    renderShell("/session/sess_real/review");
    expect(screen.queryByRole("navigation", { name: "页脚导航" })).toBeInTheDocument();
  });
});
