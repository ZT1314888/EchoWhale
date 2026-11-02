import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Footer } from "./Footer";

describe("Footer", () => {
  it("renders the brand mark, the three app links and the copyright", () => {
    render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "页脚导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Practice" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute("href", "/history");
    expect(screen.getByRole("link", { name: "Progress" })).toHaveAttribute("href", "/progress");
    expect(screen.getByText("© 2026 EchoWhale")).toBeInTheDocument();
  });
});
