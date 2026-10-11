import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QuickReplyChips } from "./QuickReplyChips";

describe("QuickReplyChips", () => {
  it("renders nothing when there are no replies", () => {
    const { container } = render(<QuickReplyChips replies={[]} onPick={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("hands the picked reply back to the caller", () => {
    const onPick = vi.fn();
    render(<QuickReplyChips replies={["Could you say that again?"]} onPick={onPick} />);

    fireEvent.click(screen.getByRole("button", { name: "Could you say that again?" }));

    expect(onPick).toHaveBeenCalledWith("Could you say that again?");
  });

  it("disables every chip while a turn is in flight", () => {
    const onPick = vi.fn();
    render(<QuickReplyChips replies={["Let me think."]} onPick={onPick} disabled />);

    const chip = screen.getByRole("button", { name: "Let me think." });
    expect(chip).toBeDisabled();
    fireEvent.click(chip);
    expect(onPick).not.toHaveBeenCalled();
  });
});
