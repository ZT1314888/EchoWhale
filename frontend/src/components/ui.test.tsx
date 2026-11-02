import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, Eyebrow, PageShell, RadarChart, ScoreBar, ScoreRing, SectionTitle, Stat } from "./ui";

describe("ui primitives", () => {
  it("PageShell narrows by default and widens on demand", () => {
    const { container, rerender } = render(
      <PageShell>
        <p>body</p>
      </PageShell>,
    );
    expect(container.firstElementChild?.className).toContain("max-w-5xl");

    rerender(
      <PageShell wide>
        <p>body</p>
      </PageShell>,
    );
    expect(container.firstElementChild?.className).toContain("max-w-7xl");
  });

  it("Eyebrow and SectionTitle switch their tone with dark", () => {
    const { container, rerender } = render(<Eyebrow>Plain</Eyebrow>);
    expect(container.firstElementChild?.className).toContain("bg-white/70");

    rerender(<Eyebrow dark>Dark</Eyebrow>);
    expect(container.firstElementChild?.className).toContain("bg-white/10");

    rerender(<SectionTitle en="Recent" cn="最近" />);
    expect(screen.getByRole("heading", { level: 2, name: /Recent/ })).toBeInTheDocument();
    expect(screen.queryByText("desc")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 }).className).toContain("text-[#131311]");

    rerender(<SectionTitle en="Recent" cn="最近" desc="desc" dark />);
    expect(screen.getByText("desc")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 }).className).toContain("text-white");
  });

  it("ScoreRing clamps the arc and picks a colour per band", () => {
    const strokeOf = (container: HTMLElement) =>
      Array.from(container.querySelectorAll("circle"))[1].getAttribute("stroke");

    const cases: [number, string][] = [
      [86, "#059669"],
      [70, "#4f46e5"],
      [55, "#d97706"],
      [54, "#e11d48"],
    ];

    for (const [score, color] of cases) {
      const { container, unmount } = render(<ScoreRing score={score} />);
      expect(strokeOf(container)).toBe(color);
      expect(screen.getByText(String(score))).toBeInTheDocument();
      unmount();
    }

    const { container } = render(<ScoreRing score={320} label="—" dark />);
    expect(container.querySelectorAll("circle")[0].getAttribute("stroke")).toBe("rgba(255,255,255,0.14)");
    expect(strokeOf(container)).toBe("#059669");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("ScoreBar renders the score and its bar width", () => {
    const { container } = render(<ScoreBar label="Grammar" cn="语法" score={42} />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("语法")).toBeInTheDocument();
    const fills = Array.from(container.querySelectorAll<HTMLElement>("div[style]"));
    expect(fills.some((el) => el.style.width === "42%")).toBe(true);
  });

  it("RadarChart labels each axis and exposes an image role", () => {
    render(
      <RadarChart
        scores={[
          { label: "Fluency", value: 0 },
          { label: "Grammar", value: 0 },
          { label: "Vocabulary", value: 0 },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "能力雷达图" })).toBeInTheDocument();
    expect(screen.getByText("Fluency")).toBeInTheDocument();
  });

  it("Stat shows an optional sub line", () => {
    const { rerender } = render(<Stat value="0" label="Sessions" />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("已加载")).not.toBeInTheDocument();

    rerender(<Stat value="0" label="Sessions" sub="已加载" />);
    expect(screen.getByText("已加载")).toBeInTheDocument();
  });

  it("EmptyState shows the action only when one is supplied", () => {
    const { rerender } = render(<EmptyState icon={<span>i</span>} title="还没开始" desc="先去上传一张图片。" />);
    expect(screen.getByText("还没开始")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    rerender(
      <EmptyState icon={<span>i</span>} title="还没开始" desc="先去上传一张图片。" action={<a href="/">去上传</a>} />,
    );
    expect(screen.getByRole("link", { name: "去上传" })).toBeInTheDocument();
  });
});
