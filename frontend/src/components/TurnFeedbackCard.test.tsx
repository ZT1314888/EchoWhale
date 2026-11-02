import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TurnFeedbackCard } from "./TurnFeedbackCard";

const feedback = {
  grammar: { title: "Grammar", body: "Your meaning is clear." },
  moreNatural: { title: "More Natural", body: "Could I get an iced latte, please?" },
  usefulWords: { title: "Useful Words", words: ["iced latte"], body: "把这些词带进下一轮回答。" },
  nextStep: { title: "Next Step", body: "下一轮补一句细节。" },
};

describe("TurnFeedbackCard", () => {
  it("renders the live card with the header", () => {
    render(<TurnFeedbackCard feedback={feedback} />);

    expect(screen.getByTestId("turn-feedback-card")).toBeInTheDocument();
    expect(screen.getByText("本轮反馈")).toBeInTheDocument();
    expect(screen.getByText("Your meaning is clear.")).toBeInTheDocument();
    expect(screen.getByText("iced latte")).toBeInTheDocument();
    expect(screen.getByText("下一轮补一句细节。")).toBeInTheDocument();
  });

  it("renders the compact inline card without the header", () => {
    render(<TurnFeedbackCard feedback={feedback} compact />);

    expect(screen.getByTestId("message-feedback-card")).toBeInTheDocument();
    expect(screen.queryByText("本轮反馈")).not.toBeInTheDocument();
    expect(screen.getByText("Could I get an iced latte, please?")).toBeInTheDocument();
    expect(screen.getByText("Grammar")).toBeInTheDocument();
  });
});
