import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PracticeSessionPage } from "./PracticeSessionPage";

vi.mock("../services/practiceApi", () => ({
  getPracticeSession: vi.fn(),
}));

vi.mock("../services/sessionApi", () => ({
  bootstrapVoiceSession: vi.fn(),
  completeVoiceSession: vi.fn(),
  submitPracticeTurnStream: vi.fn(),
}));

vi.mock("../hooks/useDeepgramVoiceAgent", () => ({
  useDeepgramVoiceAgent: vi.fn(),
}));

import { useDeepgramVoiceAgent } from "../hooks/useDeepgramVoiceAgent";
import { getPracticeSession } from "../services/practiceApi";
import {
  bootstrapVoiceSession,
  completeVoiceSession,
  submitPracticeTurnStream,
  type PracticeTurnStreamHandlers,
} from "../services/sessionApi";
import type { PracticeFeedback } from "../types/app";

const session = {
  id: "sess_real",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · barista",
  openingPrompt: "开场提示：Hi there, what can I get started for you today?",
  tags: ["coffee", "menu"],
  voiceTitle: "点一下，用声音回答",
  voiceBody: "页面只保留语音入口。",
  messages: [
    {
      id: "msg_1",
      role: "coach" as const,
      label: "教练 · 追问",
      content: "Hi there, what can I get started for you today?",
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
});

const sampleTurnFeedback: PracticeFeedback = {
  grammar: { title: "Grammar", body: "Your meaning is clear." },
  moreNatural: { title: "More Natural", body: "Could I get an iced latte, please?" },
  usefulWords: { title: "Useful Words", words: ["iced latte"], body: "把这些词带进下一轮回答。" },
  nextStep: { title: "Next Step", body: "下一轮再补一句细节。" },
};

function baseVoiceState() {
  return {
    error: "",
    isConnected: false,
    isListening: false,
    isThinking: false,
    isSpeaking: false,
    transcript: [] as Array<{ role: "assistant" | "user"; content: string }>,
    startSession: vi.fn().mockResolvedValue(undefined),
    endSession: vi.fn().mockResolvedValue({
      conversation: [],
      terminationReason: "user_ended",
      clientDiagnostics: {},
    }),
  };
}

function renderSessionPage() {
  return render(
    <MemoryRouter initialEntries={["/session/sess_real"]}>
      <Routes>
        <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
        <Route path="/session/:sessionId/review" element={<div>Review Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PracticeSessionPage", () => {
  it("renders the icon-only aside and keeps the conversation pinned to the latest message", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    const voiceState = {
      error: "",
      isConnected: false,
      isListening: false,
      isThinking: false,
      isSpeaking: false,
      transcript: [] as Array<{ role: "assistant" | "user"; content: string }>,
      startSession: vi.fn().mockResolvedValue(undefined),
      endSession: vi.fn().mockResolvedValue({
        conversation: [],
        terminationReason: "user_ended",
        clientDiagnostics: {},
      }),
    };

    vi.mocked(getPracticeSession).mockResolvedValue(session);
    vi.mocked(useDeepgramVoiceAgent).mockImplementation(() => voiceState);

    const view = render(
      <MemoryRouter initialEntries={["/session/sess_real"]}>
        <Routes>
          <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    expect(screen.getByTestId("session-aside")).toBeInTheDocument();
    expect(screen.getByTestId("session-conversation-panel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start voice practice/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /talk to your agent/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/opening prompt/i)).not.toBeInTheDocument();

    voiceState.transcript = [{ role: "assistant", content: "Can you give me a quick status update?" }];
    view.rerender(
      <MemoryRouter initialEntries={["/session/sess_real"]}>
        <Routes>
          <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
  });

  it("uses the logo button as the single start and end control", async () => {
    vi.mocked(getPracticeSession).mockResolvedValue(session);
    vi.mocked(bootstrapVoiceSession).mockResolvedValue({
      sessionId: "sess_real",
      deepgramAccessToken: "dg-token",
      deepgramWsUrl: "wss://api.deepgram.com/v1/agent/converse",
      expiresIn: 600,
      agentSettings: { type: "Settings" },
      session,
    });
    vi.mocked(completeVoiceSession).mockResolvedValue({
      session: {
        ...session,
        messages: [
          ...session.messages,
          {
            id: "msg_2",
            role: "learner" as const,
            label: "你 · 本轮回答",
            content: "Could I get an iced latte, please?",
          },
        ],
      },
      review: {
        sessionId: "sess_real",
        title: "本轮回响",
        highlight: "你已经说清楚主要需求。",
        nextTry: "下一轮再补一条细节。",
        feedback: {
          grammar: { title: "Grammar", body: "Your meaning is clear." },
          moreNatural: { title: "More Natural", body: "Could I get an iced latte, please?" },
          usefulWords: {
            title: "Useful Words",
            words: ["latte", "size", "iced"],
            body: "把这些词带进下一轮回答，会更自然。",
          },
          nextStep: { title: "Next Step", body: "下一轮试着在一句主回应后再补一句细节。" },
        },
      },
    });
    vi.mocked(useDeepgramVoiceAgent).mockReturnValue({
      error: "",
      isConnected: false,
      isListening: false,
      isThinking: false,
      isSpeaking: false,
      transcript: [
        { role: "assistant", content: "Hi there, what can I get started for you today?" },
        { role: "user", content: "Could I get an iced latte, please?" },
      ],
      startSession: vi.fn().mockResolvedValue(undefined),
      endSession: vi.fn().mockResolvedValue({
        conversation: [
          { role: "assistant", content: "Hi there, what can I get started for you today?" },
          { role: "user", content: "Could I get an iced latte, please?" },
        ],
        terminationReason: "user_ended",
        clientDiagnostics: {
          browser: "Edge 135",
          last_agent_event: "AgentAudioDone",
        },
      }),
    });

    render(
      <MemoryRouter initialEntries={["/session/sess_real"]}>
        <Routes>
          <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
          <Route path="/session/:sessionId/review" element={<div>Review Page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start voice practice/i }));

    await waitFor(() => {
      expect(bootstrapVoiceSession).toHaveBeenCalledWith("sess_real");
    });
    expect(screen.getByRole("button", { name: /end voice practice/i })).toHaveAttribute("data-state", "live");

    fireEvent.click(screen.getByRole("button", { name: /end voice practice/i }));

    await waitFor(() => {
      expect(completeVoiceSession).toHaveBeenCalledWith("sess_real", {
        conversation: [
          { role: "assistant", content: "Hi there, what can I get started for you today?" },
          { role: "user", content: "Could I get an iced latte, please?" },
        ],
        terminationReason: "user_ended",
        clientDiagnostics: {
          browser: "Edge 135",
          last_agent_event: "AgentAudioDone",
        },
      });
    });
    expect(await screen.findByText("Review Page")).toBeInTheDocument();
  });

  it("streams a text turn: live feedback card first, deltas, then inline persisted feedback", async () => {
    const streamResult = {
      messages: [
        ...session.messages,
        {
          id: "msg_2",
          role: "learner" as const,
          label: "你 · 本轮回答",
          content: "Could I get an iced latte, please?",
        },
        {
          id: "msg_3",
          role: "coach" as const,
          label: "教练 · 追问",
          content: "Sure. What size would you like?",
          feedback: sampleTurnFeedback,
        },
      ],
      feedback: sampleTurnFeedback,
    };
    let release!: (value: typeof streamResult) => void;
    const pending = new Promise<typeof streamResult>((resolve) => {
      release = resolve;
    });
    let captured: PracticeTurnStreamHandlers | undefined;
    vi.mocked(getPracticeSession).mockResolvedValue(session);
    vi.mocked(useDeepgramVoiceAgent).mockReturnValue(baseVoiceState());
    vi.mocked(submitPracticeTurnStream).mockImplementation((_sessionId, _input, handlers) => {
      captured = handlers;
      return pending;
    });

    renderSessionPage();

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "Could I get an iced latte, please?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    await waitFor(() => {
      expect(submitPracticeTurnStream).toHaveBeenCalledWith(
        "sess_real",
        { content: "Could I get an iced latte, please?" },
        expect.anything(),
        expect.anything(),
      );
    });
    expect(screen.getByRole("button", { name: /start voice practice/i })).toBeDisabled();

    act(() => {
      captured?.onFeedback?.(sampleTurnFeedback);
    });
    expect(await screen.findByTestId("turn-feedback-card")).toBeInTheDocument();

    act(() => {
      captured?.onDelta?.("Sure. ");
    });
    expect(await screen.findByTestId("coach-stream-bubble")).toBeInTheDocument();
    expect(screen.queryByText(/What size would you like\?/)).not.toBeInTheDocument();

    act(() => {
      captured?.onDelta?.("What size would you like?");
    });
    expect(await screen.findByText(/What size would you like\?/)).toBeInTheDocument();

    await act(async () => {
      release(streamResult);
    });

    expect(await screen.findByText("Sure. What size would you like?")).toBeInTheDocument();
    expect(screen.queryByTestId("coach-stream-bubble")).not.toBeInTheDocument();
    // 落库后反馈以内联卡片挂在消息上，悬浮卡退场。
    expect(screen.getAllByTestId("message-feedback-card")).toHaveLength(1);
    expect(screen.queryByTestId("turn-feedback-card")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("");
    expect(screen.getByRole("button", { name: /start voice practice/i })).toBeEnabled();
  });

  it("surfaces a structured error and keeps the draft when a text turn fails", async () => {
    vi.mocked(getPracticeSession).mockResolvedValue(session);
    vi.mocked(useDeepgramVoiceAgent).mockReturnValue(baseVoiceState());
    vi.mocked(submitPracticeTurnStream).mockRejectedValue({
      code: "TURN_SUBMIT_FAILED",
      message: "生成服务暂时不可用，请稍后再试。",
    });

    renderSessionPage();

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "Could I get an iced latte, please?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    expect(await screen.findByText("生成服务暂时不可用，请稍后再试。")).toBeInTheDocument();
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("Could I get an iced latte, please?");
    expect(screen.getByRole("button", { name: /发送/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /start voice practice/i })).toBeEnabled();
  });

  it("aborts an in-flight text turn and clears the live bubbles", async () => {
    let captured: PracticeTurnStreamHandlers | undefined;
    vi.mocked(getPracticeSession).mockResolvedValue(session);
    vi.mocked(useDeepgramVoiceAgent).mockReturnValue(baseVoiceState());
    vi.mocked(submitPracticeTurnStream).mockImplementation(
      (_sessionId, _input, handlers, signal) => {
        captured = handlers;
        return new Promise((_resolve, reject) => {
          signal?.addEventListener("abort", () => {
            const abortError = new Error("aborted");
            abortError.name = "AbortError";
            reject(abortError);
          });
        });
      },
    );

    renderSessionPage();

    expect(await screen.findByText(/咖啡店柜台点单/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "Could I get an iced latte, please?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    await waitFor(() => {
      expect(submitPracticeTurnStream).toHaveBeenCalled();
    });
    act(() => {
      captured?.onFeedback?.(sampleTurnFeedback);
      captured?.onDelta?.("Sure. ");
    });
    expect(await screen.findByTestId("coach-stream-bubble")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /取消/i }));

    await waitFor(() => {
      expect(screen.queryByTestId("coach-stream-bubble")).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("turn-feedback-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-live-bubble")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("Could I get an iced latte, please?");
    expect(screen.getByRole("button", { name: /发送/i })).toBeEnabled();
    expect(screen.queryByText(/发送失败/)).not.toBeInTheDocument();
  });

});
