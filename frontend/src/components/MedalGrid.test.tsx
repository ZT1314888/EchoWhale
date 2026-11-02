import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildMedals } from "../utils/progressStats";
import { MedalGrid } from "./MedalGrid";

describe("MedalGrid", () => {
  it("shows every medal locked with its unlock requirement for a fresh learner", () => {
    render(<MedalGrid medals={buildMedals(0)} />);

    expect(screen.getByText("0 / 6 已解锁")).toBeInTheDocument();
    expect(screen.getByText("首次开口")).toBeInTheDocument();
    expect(screen.getByText("至少 1 轮")).toBeInTheDocument();
    expect(screen.queryByText("已解锁")).not.toBeInTheDocument();
  });

  it("marks the medals the backend can actually back", () => {
    render(<MedalGrid medals={buildMedals(12)} />);

    expect(screen.getByText("2 / 6 已解锁")).toBeInTheDocument();
    expect(screen.getAllByText("已解锁")).toHaveLength(2);
  });

  it("keeps the four unbacked medals locked and says which field is missing", () => {
    render(<MedalGrid medals={buildMedals(999)} />);

    expect(screen.getByText("需要连击字段")).toBeInTheDocument();
    expect(screen.getByText("需要词数字段")).toBeInTheDocument();
    expect(screen.getByText("需要评分字段")).toBeInTheDocument();
    expect(screen.getByText("需要目标字段")).toBeInTheDocument();
  });
});
