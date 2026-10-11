import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PhraseBank } from "./PhraseBank";

describe("PhraseBank", () => {
  it("renders nothing when there are no phrases", () => {
    const { container } = render(<PhraseBank phrases={[]} onInsert={vi.fn()} onDismiss={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("inserts a phrase into the composer draft", () => {
    const onInsert = vi.fn();
    render(<PhraseBank phrases={["To be honest, I think…"]} onInsert={onInsert} onDismiss={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /To be honest, I think…/ }));

    expect(onInsert).toHaveBeenCalledWith("To be honest, I think…");
  });

  it("can be dismissed", () => {
    const onDismiss = vi.fn();
    render(<PhraseBank phrases={["What I mean is…"]} onInsert={vi.fn()} onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole("button", { name: "收起金句锦囊" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
