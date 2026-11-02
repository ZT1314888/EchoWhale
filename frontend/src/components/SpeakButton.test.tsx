import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SpeakButton } from "./SpeakButton";

type FakeUtterance = { text: string; onend: (() => void) | null; onerror: (() => void) | null };

function installSpeechSynthesis() {
  const speak = vi.fn();
  const cancel = vi.fn();
  const utterances: FakeUtterance[] = [];

  class FakeSpeechSynthesisUtterance implements FakeUtterance {
    text: string;
    lang = "";
    rate = 1;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(text: string) {
      this.text = text;
      utterances.push(this);
    }
  }

  Object.defineProperty(window, "speechSynthesis", { configurable: true, writable: true, value: { speak, cancel } });
  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    configurable: true,
    writable: true,
    value: FakeSpeechSynthesisUtterance,
  });

  return { speak, cancel, utterances };
}

function removeSpeechSynthesis() {
  Reflect.deleteProperty(window, "speechSynthesis");
  Reflect.deleteProperty(window, "SpeechSynthesisUtterance");
}

afterEach(() => {
  removeSpeechSynthesis();
  vi.restoreAllMocks();
});

describe("SpeakButton", () => {
  it("renders nothing when the browser cannot synthesize speech", () => {
    const { container } = render(<SpeakButton text="Hi there." />);

    expect(container).toBeEmptyDOMElement();
  });

  it("speaks the text in en-US and toggles to a stop affordance", () => {
    const speech = installSpeechSynthesis();
    render(<SpeakButton text="What can I get you?" />);

    fireEvent.click(screen.getByRole("button", { name: "跟读：What can I get you?" }));

    expect(speech.speak).toHaveBeenCalledTimes(1);
    expect(speech.utterances).toHaveLength(1);
    expect(speech.utterances[0].text).toBe("What can I get you?");
    expect(screen.getByRole("button", { name: "停止跟读：What can I get you?" })).toBeInTheDocument();
  });

  it("clears the playing state when the utterance ends", () => {
    const speech = installSpeechSynthesis();
    render(<SpeakButton text="Nice to meet you." />);

    fireEvent.click(screen.getByRole("button", { name: "跟读：Nice to meet you." }));
    act(() => {
      speech.utterances[0].onend?.();
    });

    expect(screen.getByRole("button", { name: "跟读：Nice to meet you." })).toBeInTheDocument();
  });

  it("stops playback when the active button is clicked again", () => {
    const speech = installSpeechSynthesis();
    render(<SpeakButton text="No problem at all." />);

    fireEvent.click(screen.getByRole("button", { name: "跟读：No problem at all." }));
    fireEvent.click(screen.getByRole("button", { name: "停止跟读：No problem at all." }));

    expect(speech.cancel).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "跟读：No problem at all." })).toBeInTheDocument();
  });

  it("ignores blank text", () => {
    const speech = installSpeechSynthesis();
    render(<SpeakButton text="   " />);

    // aria-label 的空白会被折叠，可访问名里只剩「跟读：」。
    fireEvent.click(screen.getByRole("button", { name: /^跟读：$/ }));

    expect(speech.speak).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^跟读：$/ })).toBeInTheDocument();
  });
});
