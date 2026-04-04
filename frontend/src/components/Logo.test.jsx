import { render, screen } from "@testing-library/react";

import { Logo } from "./Logo";

describe("Logo", () => {
  it("renders the whale svg with an accessible name", () => {
    render(<Logo title="EchoWhale brand mark" />);

    expect(screen.getByRole("img", { name: /echowhale brand mark/i })).toBeInTheDocument();
  });
});
