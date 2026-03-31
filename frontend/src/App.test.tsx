import { render, screen } from "@testing-library/react";

import { App } from "./App";

describe("App", () => {
  it("renders the core EchoWhale workflow surfaces", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /echowhale/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/upload today's scene/i)).toBeInTheDocument();
    expect(screen.getByText(/practice cockpit/i)).toBeInTheDocument();
    expect(screen.getByText(/history review/i)).toBeInTheDocument();
    expect(screen.getByText(/grammar rescue/i)).toBeInTheDocument();
  });
});
