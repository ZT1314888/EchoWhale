import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDeepgramVoiceAgent } from "./useDeepgramVoiceAgent";
import type { VoiceBootstrapResult } from "../types/app";

const session = {
  id: "sess_real",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · barista",
  openingPrompt: "开场提示：Hi there, what can I get started for you today?",
  tags: ["coffee", "menu"],
  liveHint: "先用一句短句回应，再补一条细节，会更稳。",
  voiceTitle: "点一下，用声音回答",
  voiceBody: "页面只保留语音入口。",
  messages: [],
};

const bootstrap: VoiceBootstrapResult = {
  sessionId: "sess_real",
  deepgramAccessToken: "dg-token",
  deepgramWsUrl: "wss://api.deepgram.com/v1/agent/converse",
  expiresIn: 600,
  agentSettings: { type: "Settings" },
  session,
};

const originalWebSocket = globalThis.WebSocket;
const originalAudioContext = window.AudioContext;
const originalWebkitAudioContext = window.webkitAudioContext;
const originalMediaDevices = navigator.mediaDevices;

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static autoError = true;

  url: string;
  protocols: string | string[] | undefined;
  binaryType = "";
  readyState: number = WebSocket.CONNECTING;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  sent: unknown[] = [];

  constructor(url: string | URL, protocols?: string | string[]) {
    this.url = String(url);
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
    if (MockWebSocket.autoError) {
      queueMicrotask(() => {
        this.onerror?.(new Event("error"));
      });
    }
  }

  send(data: unknown): void {
    this.sent.push(data);
  }

  close(): void {
    this.dispatchClose();
  }

  dispatchJson(payload: Record<string, unknown>): void {
    this.onmessage?.(
      {
        data: JSON.stringify(payload),
      } as MessageEvent,
    );
  }

  dispatchClose(reason = "", code = 1000): void {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { reason, code }));
  }
}

class FakeConnectable {
  connections: unknown[] = [];

  connect(target: unknown): unknown {
    this.connections.push(target);
    return target;
  }

  disconnect(): void {
    this.connections = [];
  }
}

class FakeMediaStreamSource extends FakeConnectable {}

class FakeScriptProcessor extends FakeConnectable {
  onaudioprocess: ((event: AudioProcessingEvent) => void) | null = null;
  bufferSize = 0;
}

class FakeGainNode extends FakeConnectable {
  gain = { value: 1 };
}

class FakeBufferSource extends FakeConnectable {
  static instances: FakeBufferSource[] = [];

  buffer: AudioBuffer | null = null;
  onended: (() => void) | null = null;
  startTimes: number[] = [];

  constructor() {
    super();
    FakeBufferSource.instances.push(this);
  }

  start(when?: number): void {
    this.startTimes.push(when ?? 0);
    this.onended?.();
  }

  stop(): void {}
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];

  sampleRate: number;
  latencyHint?: AudioContextLatencyCategory | number;
  currentTime = 1;
  destination = { type: "destination" };
  sourceNode = new FakeMediaStreamSource();
  processorNode = new FakeScriptProcessor();
  gainNode = new FakeGainNode();
  resumed = false;
  createScriptProcessorArgs: [number, number, number] | null = null;

  constructor(options?: AudioContextOptions) {
    this.sampleRate = options?.sampleRate ?? 48000;
    this.latencyHint = options?.latencyHint;
    FakeAudioContext.instances.push(this);
  }

  createMediaStreamSource(): MediaStreamAudioSourceNode {
    return this.sourceNode as unknown as MediaStreamAudioSourceNode;
  }

  createScriptProcessor(
    bufferSize?: number,
    inputChannels?: number,
    outputChannels?: number,
  ): ScriptProcessorNode {
    this.createScriptProcessorArgs = [
      bufferSize ?? 0,
      inputChannels ?? 0,
      outputChannels ?? 0,
    ];
    this.processorNode.bufferSize = bufferSize ?? 0;
    return this.processorNode as unknown as ScriptProcessorNode;
  }

  createGain(): GainNode {
    return this.gainNode as unknown as GainNode;
  }

  createBuffer(_channels: number, length: number): AudioBuffer {
    return {
      getChannelData: () => new Float32Array(length),
    } as unknown as AudioBuffer;
  }

  createBufferSource(): AudioBufferSourceNode {
    return new FakeBufferSource() as unknown as AudioBufferSourceNode;
  }

  async resume(): Promise<void> {
    this.resumed = true;
  }

  async close(): Promise<void> {}
}

function installAudioMocks(): void {
  window.AudioContext = FakeAudioContext as unknown as typeof AudioContext;
  window.webkitAudioContext = FakeAudioContext as unknown as typeof AudioContext;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({
        getAudioTracks: () => [
          {
            getSettings: () => ({
              channelCount: 1,
              sampleRate: 16000,
            }),
            stop: vi.fn(),
          },
        ],
        getTracks: () => [{ stop: vi.fn() }],
      }),
    },
  });
}

afterEach(() => {
  vi.useRealTimers();
  globalThis.WebSocket = originalWebSocket;
  window.AudioContext = originalAudioContext;
  window.webkitAudioContext = originalWebkitAudioContext;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: originalMediaDevices,
  });
  FakeAudioContext.instances = [];
  FakeBufferSource.instances = [];
  MockWebSocket.instances = [];
  MockWebSocket.autoError = true;
  vi.restoreAllMocks();
});

describe("useDeepgramVoiceAgent", () => {
  it("opens the Voice Agent websocket with bearer subprotocols instead of query params", async () => {
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    let startOutcome: Promise<unknown>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      startOutcome = startPromise.catch((error: Error) => error);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0]?.url).toBe("wss://api.deepgram.com/v1/agent/converse");
    expect(MockWebSocket.instances[0]?.protocols).toEqual(["bearer", "dg-token"]);
    await expect(startOutcome!).resolves.toMatchObject({
      message: "语音会话连接失败，请稍后再试。",
    });
  });

  it("captures audio through a silent gain node with low-latency constraints after SettingsApplied", async () => {
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    installAudioMocks();

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    expect(ws).toBeDefined();

    await act(async () => {
      ws?.dispatchJson({ type: "Welcome" });
      ws?.dispatchJson({ type: "SettingsApplied" });
      await startPromise!;
    });

    const inputContext = FakeAudioContext.instances.find((item) => item.sampleRate === 48000);
    expect(inputContext).toBeDefined();
    expect(inputContext?.resumed).toBe(true);
    expect(inputContext?.latencyHint).toBe("interactive");
    expect(inputContext?.createScriptProcessorArgs).toEqual([1024, 1, 1]);
    expect(ws?.sent[0]).toBe(JSON.stringify(bootstrap.agentSettings));
    expect(inputContext?.sourceNode.connections).toEqual([inputContext?.processorNode]);
    expect(inputContext?.processorNode.connections).toEqual([inputContext?.gainNode]);
    expect(inputContext?.gainNode.gain.value).toBe(0);
    expect(inputContext?.gainNode.connections).toEqual([inputContext?.destination]);
    expect(inputContext?.processorNode.connections).not.toContain(inputContext?.destination);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: {
        autoGainControl: false,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: { ideal: 16000 },
      },
    });
  });

  it("rejects startup when the websocket closes before initialization completes", async () => {
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    let startOutcome: Promise<string>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      startOutcome = startPromise.then(
        () => "resolved",
        (error: Error) => error.message,
      );
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    await act(async () => {
      ws?.dispatchClose();
    });

    const outcome = await Promise.race([
      startOutcome!,
      new Promise<string>((resolve) => {
        window.setTimeout(() => resolve("pending"), 20);
      }),
    ]);

    expect(outcome).toBe("语音会话在初始化阶段被关闭，请检查 Deepgram think 配置或后端代理日志。");
  });

  it("rejects startup when SettingsApplied does not arrive before the init timeout", async () => {
    vi.useFakeTimers();
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startOutcome: Promise<string>;
    await act(async () => {
      startOutcome = result.current.startSession(bootstrap).then(
        () => "resolved",
        (error: Error) => error.message,
      );
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    await act(async () => {
      ws?.dispatchJson({ type: "Welcome" });
      await vi.advanceTimersByTimeAsync(10_001);
    });

    await expect(startOutcome!).resolves.toBe("语音会话初始化超时，请稍后重试。");
    expect(result.current.error).toBe("语音会话初始化超时，请稍后重试。");
    expect(result.current.isConnected).toBe(false);
  });

  it("exits the thinking state when the agent stalls for too long", async () => {
    vi.useFakeTimers();
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    installAudioMocks();

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    await act(async () => {
      ws?.dispatchJson({ type: "Welcome" });
      ws?.dispatchJson({ type: "SettingsApplied" });
      await startPromise!;
    });

    await act(async () => {
      ws?.dispatchJson({ type: "AgentThinking" });
      await vi.advanceTimersByTimeAsync(12_001);
    });

    expect(result.current.error).toBe("语音代理响应超时，请重试本轮对话。");
    expect(result.current.isThinking).toBe(false);
    expect(result.current.isListening).toBe(false);
  });

  it("schedules playback continuously with a small safety buffer", async () => {
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    installAudioMocks();

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    await act(async () => {
      ws?.dispatchJson({ type: "Welcome" });
      ws?.dispatchJson({ type: "SettingsApplied" });
      await startPromise!;
    });

    const firstChunk = new Int16Array(2400).buffer;
    const secondChunk = new Int16Array(2400).buffer;

    await act(async () => {
      ws?.onmessage?.({ data: firstChunk } as MessageEvent);
      ws?.onmessage?.({ data: secondChunk } as MessageEvent);
      await Promise.resolve();
    });

    expect(FakeBufferSource.instances).toHaveLength(2);
    expect(FakeBufferSource.instances[0]?.startTimes).toEqual([1.03]);
    expect(FakeBufferSource.instances[1]?.startTimes[0]).toBeCloseTo(1.13, 6);
  });

  it("includes low-latency diagnostics when ending a session", async () => {
    MockWebSocket.autoError = false;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    installAudioMocks();

    const { result } = renderHook(() => useDeepgramVoiceAgent());
    let startPromise: Promise<void>;
    await act(async () => {
      startPromise = result.current.startSession(bootstrap);
      await Promise.resolve();
    });
    const ws = MockWebSocket.instances[0];

    await act(async () => {
      ws?.dispatchJson({ type: "Welcome" });
      ws?.dispatchJson({ type: "SettingsApplied" });
      await startPromise!;
    });

    await act(async () => {
      ws?.onmessage?.({ data: new Int16Array(2400).buffer } as MessageEvent);
      await Promise.resolve();
    });

    let endResult:
      | {
          clientDiagnostics: Record<string, unknown>;
        }
      | undefined;

    await act(async () => {
      endResult = await result.current.endSession();
    });

    expect(endResult?.clientDiagnostics).toMatchObject({
      constraints_fallback_used: false,
      input_channel_count: 1,
      input_context_sample_rate: 48000,
      output_sample_rate: 24000,
      playback_gap_resets: 1,
      processor_buffer_size: 1024,
      track_sample_rate: 16000,
    });
    expect(endResult?.clientDiagnostics.last_playback_schedule_lag_ms).toBe(0);
  });
});
