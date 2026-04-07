import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PracticeSessionPage } from "./PracticeSessionPage";

vi.mock("../services/practiceApi", () => ({
  getPracticeSession: vi.fn(),
}));

vi.mock("../services/sessionApi", () => ({
  bootstrapVoiceSession: vi.fn(),
  completeVoiceSession: vi.fn(),
}));

vi.mock("../hooks/useDeepgramVoiceAgent", () => ({
  useDeepgramVoiceAgent: vi.fn(),
}));

import { useDeepgramVoiceAgent } from "../hooks/useDeepgramVoiceAgent";
import { getPracticeSession } from "../services/practiceApi";
import { bootstrapVoiceSession, completeVoiceSession } from "../services/sessionApi";

const session = {
  id: "sess_real",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · barista",
  openingPrompt: "开场提示：Hi there, what can I get started for you today?",
  tags: ["coffee", "menu"],
  liveHint: "先用一句短句回应，再补一条细节，会更稳。",
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

describe("PracticeSessionPage", () => {
  it("starts with Deepgram bootstrap and completes with voice transcript persistence", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /talk to your agent/i }));

    await waitFor(() => {
      expect(bootstrapVoiceSession).toHaveBeenCalledWith("sess_real");
    });

    fireEvent.click(screen.getByRole("button", { name: /end conversation/i }));

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
});
