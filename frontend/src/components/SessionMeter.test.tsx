import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionMeter } from "./SessionMeter";

afterEach(() => {
  vi.useRealTimers();
});

describe("SessionMeter", () => {
  it("shows the opening count and a clock that ticks once per second", () => {
    vi.useFakeTimers();
    render(<SessionMeter turnCount={3} />);

    expect(screen.getByText("3 轮")).toBeInTheDocument();
    expect(screen.getByText("00:00")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(65_000);
    });

    expect(screen.getByText("01:05")).toBeInTheDocument();
  });

  it("stops counting once unmounted", () => {
    vi.useFakeTimers();
    const view = render(<SessionMeter turnCount={0} />);

    view.unmount();
    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(vi.getTimerCount()).toBe(0);
  });
});
