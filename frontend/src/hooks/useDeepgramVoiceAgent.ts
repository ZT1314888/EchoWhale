import { useEffect, useRef, useState } from "react";

import type { VoiceBootstrapResult, VoiceConversationItem } from "../types/app";

type VoiceSessionEnd = {
  conversation: VoiceConversationItem[];
  terminationReason: string;
  clientDiagnostics: Record<string, unknown>;
};

type AudioContextCtor = typeof AudioContext;
type ScriptProcessorNodeLike = ScriptProcessorNode;
type InitPhase = "idle" | "connecting" | "awaiting_settings" | "ready";

const DEFAULT_INPUT_SAMPLE_RATE = 16000;
const DEFAULT_OUTPUT_SAMPLE_RATE = 24000;
const PLAYBACK_SAFETY_BUFFER_SECONDS = 0.03;
const INPUT_BUFFER_SIZE_CANDIDATES = [1024, 2048, 4096] as const;
const SESSION_INIT_TIMEOUT_MS = 10_000;
const THINKING_STALL_TIMEOUT_MS = 12_000;

const PREFERRED_AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    autoGainControl: false,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    sampleRate: { ideal: DEFAULT_INPUT_SAMPLE_RATE },
  },
};

declare global {
  interface Window {
    webkitAudioContext?: AudioContextCtor;
  }
}

function getAudioContextCtor(): AudioContextCtor | null {
  return window.AudioContext ?? window.webkitAudioContext ?? null;
}

function getConfiguredOutputSampleRate(agentSettings: Record<string, unknown>): number {
  const audio = agentSettings.audio;
  if (!audio || typeof audio !== "object") {
    return DEFAULT_OUTPUT_SAMPLE_RATE;
  }
  const output = (audio as { output?: unknown }).output;
  if (!output || typeof output !== "object") {
    return DEFAULT_OUTPUT_SAMPLE_RATE;
  }
  const sampleRate = (output as { sample_rate?: unknown }).sample_rate;
  return typeof sampleRate === "number" ? sampleRate : DEFAULT_OUTPUT_SAMPLE_RATE;
}

function appendTranscript(
  current: VoiceConversationItem[],
  next: VoiceConversationItem,
): VoiceConversationItem[] {
  const normalized = next.content.trim();
  if (!normalized) {
    return current;
  }
  const previous = current.at(-1);
  if (previous && previous.role === next.role && previous.content === normalized) {
    return current;
  }
  return [...current, { role: next.role, content: normalized }];
}

function downsampleTo16k(buffer: Float32Array, sampleRate: number): Int16Array {
  if (sampleRate === 16000) {
    return floatTo16BitPCM(buffer);
  }

  const ratio = sampleRate / 16000;
  const length = Math.max(1, Math.round(buffer.length / ratio));
  const result = new Int16Array(length);
  let offset = 0;

  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(buffer.length, Math.floor((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let source = start; source < end; source += 1) {
      sum += buffer[source];
      count += 1;
    }
    const sample = count ? sum / count : buffer[offset] ?? 0;
    result[index] = clampToPcm(sample);
    offset = end;
  }

  return result;
}

function floatTo16BitPCM(buffer: Float32Array): Int16Array {
  const pcm = new Int16Array(buffer.length);
  for (let index = 0; index < buffer.length; index += 1) {
    pcm[index] = clampToPcm(buffer[index]);
  }
  return pcm;
}

function clampToPcm(value: number): number {
  const sample = Math.max(-1, Math.min(1, value));
  return sample < 0 ? sample * 0x8000 : sample * 0x7fff;
}

function pcm16ToAudioBuffer(context: AudioContext, chunk: ArrayBuffer): AudioBuffer {
  const pcm = new Int16Array(chunk);
  const audioBuffer = context.createBuffer(1, pcm.length, context.sampleRate);
  const channel = audioBuffer.getChannelData(0);
  for (let index = 0; index < pcm.length; index += 1) {
    channel[index] = pcm[index] / 0x8000;
  }
  return audioBuffer;
}

function parseConversationEvent(payload: Record<string, unknown>): VoiceConversationItem | null {
  const role = typeof payload.role === "string"
    ? payload.role
    : typeof payload.speaker === "string"
      ? payload.speaker
      : typeof payload.from === "string"
        ? payload.from
        : null;
  const content = typeof payload.content === "string"
    ? payload.content
    : typeof payload.text === "string"
      ? payload.text
      : typeof payload.message === "string"
        ? payload.message
        : null;

  if ((role === "assistant" || role === "user") && content) {
    return { role, content };
  }
  return null;
}

export function useDeepgramVoiceAgent() {
  const wsRef = useRef<WebSocket | null>(null);
  const keepAliveRef = useRef<number | null>(null);
  const initTimeoutRef = useRef<number | null>(null);
  const thinkingTimeoutRef = useRef<number | null>(null);
  const inputContextRef = useRef<AudioContext | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNodeLike | null>(null);
  const muteGainRef = useRef<GainNode | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const transcriptRef = useRef<VoiceConversationItem[]>([]);
  const playbackScheduleRef = useRef<Promise<void>>(Promise.resolve());
  const playbackGenerationRef = useRef(0);
  const nextPlaybackTimeRef = useRef(0);
  const playbackGapResetsRef = useRef(0);
  const lastPlaybackScheduleLagMsRef = useRef(0);
  const constraintsFallbackUsedRef = useRef(false);
  const processorBufferSizeRef = useRef<number | null>(null);
  const inputContextSampleRateRef = useRef<number | null>(null);
  const inputChannelCountRef = useRef<number | null>(null);
  const trackSampleRateRef = useRef<number | null>(null);
  const outputSampleRateRef = useRef(DEFAULT_OUTPUT_SAMPLE_RATE);
  const lastAgentEventRef = useRef("");
  const lastAgentErrorRef = useRef("");
  const initPhaseRef = useRef<InitPhase>("idle");
  const thinkingStartedAtRef = useRef<number | null>(null);
  const thinkingStallMsRef = useRef<number | null>(null);
  const sessionReadyRef = useRef(false);
  const manualCloseRef = useRef(false);
  const [transcript, setTranscript] = useState<VoiceConversationItem[]>([]);
  const [error, setError] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  useEffect(() => {
    return () => {
      void cleanup();
    };
  }, []);

  async function startSession(bootstrap: VoiceBootstrapResult): Promise<void> {
    await cleanup();
    transcriptRef.current = [];
    lastAgentEventRef.current = "";
    lastAgentErrorRef.current = "";
    initPhaseRef.current = "connecting";
    thinkingStallMsRef.current = null;
    nextPlaybackTimeRef.current = 0;
    playbackGapResetsRef.current = 0;
    lastPlaybackScheduleLagMsRef.current = 0;
    constraintsFallbackUsedRef.current = false;
    processorBufferSizeRef.current = null;
    inputContextSampleRateRef.current = null;
    inputChannelCountRef.current = null;
    trackSampleRateRef.current = null;
    outputSampleRateRef.current = getConfiguredOutputSampleRate(bootstrap.agentSettings);
    sessionReadyRef.current = false;
    manualCloseRef.current = false;
    setTranscript([]);
    setError("");
    setIsConnected(false);
    setIsListening(false);
    setIsThinking(false);
    setIsSpeaking(false);
    await ensureOutputContext();

    const ws = new WebSocket(bootstrap.deepgramWsUrl, [
      "bearer",
      bootstrap.deepgramAccessToken,
    ]);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    await new Promise<void>((resolve, reject) => {
      let settled = false;

      function handleSessionFailure(message: string): void {
        lastAgentErrorRef.current = message;
        setError(message);
        void cleanup();
      }

      function failSessionStart(message: string): void {
        handleSessionFailure(message);
        if (!settled) {
          settled = true;
          reject(new Error(message));
        }
      }

      startInitTimeout(() => {
        failSessionStart("语音会话初始化超时，请稍后重试。");
      });

      ws.onmessage = async (event) => {
        if (event.data instanceof ArrayBuffer) {
          stopThinkingTimeout();
          enqueuePlayback(event.data);
          setIsSpeaking(true);
          setIsThinking(false);
          return;
        }

        if (typeof event.data !== "string") {
          return;
        }

        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(event.data) as Record<string, unknown>;
        } catch {
          return;
        }

        const type = typeof payload.type === "string" ? payload.type : "";
        if (type) {
          lastAgentEventRef.current = type;
        }
        if (type === "Welcome") {
          initPhaseRef.current = "awaiting_settings";
          ws.send(JSON.stringify(bootstrap.agentSettings));
          return;
        }
        if (type === "SettingsApplied") {
          stopInitTimeout();
          initPhaseRef.current = "ready";
          try {
            await beginCapture(ws);
            startKeepAlive(ws);
            sessionReadyRef.current = true;
            setIsConnected(true);
            setIsListening(true);
            if (!settled) {
              settled = true;
              resolve();
            }
          } catch (captureError) {
            if (!settled) {
              settled = true;
              reject(captureError);
            }
          }
          return;
        }

        const conversation = parseConversationEvent(payload);
        if (type === "ConversationText" && conversation) {
          transcriptRef.current = appendTranscript(transcriptRef.current, conversation);
          setTranscript(transcriptRef.current);
          return;
        }

        if (type === "UserStartedSpeaking") {
          stopThinkingTimeout();
          setIsListening(true);
          setIsThinking(false);
          stopPlayback();
          return;
        }
        if (type === "AgentThinking") {
          startThinkingTimeout(() => {
            thinkingStallMsRef.current = thinkingStartedAtRef.current === null
              ? THINKING_STALL_TIMEOUT_MS
              : Date.now() - thinkingStartedAtRef.current;
            handleSessionFailure("语音代理响应超时，请重试本轮对话。");
          });
          setIsListening(false);
          setIsThinking(true);
          return;
        }
        if (type === "AgentStartedSpeaking") {
          stopThinkingTimeout();
          setIsListening(false);
          setIsThinking(false);
          setIsSpeaking(true);
          return;
        }
        if (type === "AgentAudioDone") {
          stopThinkingTimeout();
          setIsSpeaking(false);
          setIsThinking(false);
          setIsListening(true);
          return;
        }
        if (type === "Error" || type === "AgentError") {
          const message = typeof payload.description === "string"
            ? payload.description
            : typeof payload.message === "string"
              ? payload.message
              : "语音会话暂时不可用，请稍后再试。";
          if (sessionReadyRef.current) {
            handleSessionFailure(message);
            return;
          }
          failSessionStart(message);
        }
      };

      ws.onerror = () => {
        if (sessionReadyRef.current) {
          handleSessionFailure("语音会话连接失败，请稍后再试。");
          return;
        }
        failSessionStart("语音会话连接失败，请稍后再试。");
      };

      ws.onclose = (event) => {
        stopInitTimeout();
        stopThinkingTimeout();
        stopKeepAlive();
        setIsConnected(false);
        setIsListening(false);
        setIsThinking(false);
        setIsSpeaking(false);
        if (manualCloseRef.current) {
          return;
        }
        if (!sessionReadyRef.current) {
          const reason = event.reason.trim();
          failSessionStart(
            reason || lastAgentErrorRef.current || "语音会话在初始化阶段被关闭，请检查 Deepgram think 配置或后端代理日志。",
          );
          return;
        }
        if (event.reason.trim()) {
          lastAgentErrorRef.current = event.reason.trim();
          setError(event.reason.trim());
        }
      };
    });
  }

  async function endSession(): Promise<VoiceSessionEnd> {
    const result: VoiceSessionEnd = {
      conversation: [...transcriptRef.current],
      terminationReason: "user_ended",
      clientDiagnostics: buildClientDiagnostics(),
    };
    await cleanup();
    return result;
  }

  async function beginCapture(ws: WebSocket): Promise<void> {
    const AudioContextCtor = getAudioContextCtor();
    if (!AudioContextCtor) {
      throw new Error("当前浏览器不支持语音采集，请更换浏览器后重试。");
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(PREFERRED_AUDIO_CONSTRAINTS);
    } catch {
      constraintsFallbackUsedRef.current = true;
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: false,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    }
    const context = new AudioContextCtor({ latencyHint: "interactive" });
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = createLowLatencyProcessor(context);
    const muteGain = context.createGain();
    muteGain.gain.value = 0;
    processor.onaudioprocess = (event) => {
      if (ws.readyState !== WebSocket.OPEN) {
        return;
      }
      const input = event.inputBuffer.getChannelData(0);
      const pcm = downsampleTo16k(input, context.sampleRate);
      ws.send(pcm.buffer);
    };
    source.connect(processor);
    processor.connect(muteGain);
    muteGain.connect(context.destination);

    const track = stream.getAudioTracks()[0];
    const trackSettings = track?.getSettings?.();

    streamRef.current = stream;
    inputContextRef.current = context;
    sourceNodeRef.current = source;
    processorRef.current = processor;
    muteGainRef.current = muteGain;
    processorBufferSizeRef.current = processor.bufferSize;
    inputContextSampleRateRef.current = context.sampleRate;
    inputChannelCountRef.current = typeof trackSettings?.channelCount === "number"
      ? trackSettings.channelCount
      : 1;
    trackSampleRateRef.current = typeof trackSettings?.sampleRate === "number"
      ? trackSettings.sampleRate
      : DEFAULT_INPUT_SAMPLE_RATE;
  }

  function enqueuePlayback(chunk: ArrayBuffer): void {
    const generation = playbackGenerationRef.current;
    playbackScheduleRef.current = playbackScheduleRef.current.then(
      async () => {
        const context = await ensureOutputContext();
        if (!context || generation !== playbackGenerationRef.current) {
          return;
        }
        const source = context.createBufferSource();
        activeSourcesRef.current.push(source);
        const audioBuffer = pcm16ToAudioBuffer(context, chunk);
        source.buffer = audioBuffer;
        source.connect(context.destination);
        source.onended = () => {
          activeSourcesRef.current = activeSourcesRef.current.filter((item) => item !== source);
        };
        if (generation !== playbackGenerationRef.current) {
          source.disconnect();
          return;
        }
        const schedule = getPlaybackSchedule(context, chunk.byteLength, audioBuffer.duration);
        source.start(schedule.startTime);
        nextPlaybackTimeRef.current = schedule.nextPlaybackTime;
      },
    );
  }

  function stopPlayback(): void {
    playbackGenerationRef.current += 1;
    for (const source of activeSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // Ignore already-finished sources.
      }
      source.disconnect();
    }
    activeSourcesRef.current = [];
    playbackScheduleRef.current = Promise.resolve();
    nextPlaybackTimeRef.current = 0;
    setIsSpeaking(false);
  }

  function startKeepAlive(ws: WebSocket): void {
    stopKeepAlive();
    keepAliveRef.current = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "KeepAlive" }));
      }
    }, 5000);
  }

  function stopKeepAlive(): void {
    if (keepAliveRef.current !== null) {
      window.clearInterval(keepAliveRef.current);
      keepAliveRef.current = null;
    }
  }

  function startInitTimeout(onTimeout: () => void): void {
    stopInitTimeout();
    initTimeoutRef.current = window.setTimeout(onTimeout, SESSION_INIT_TIMEOUT_MS);
  }

  function stopInitTimeout(): void {
    if (initTimeoutRef.current !== null) {
      window.clearTimeout(initTimeoutRef.current);
      initTimeoutRef.current = null;
    }
  }

  function startThinkingTimeout(onTimeout: () => void): void {
    stopThinkingTimeout();
    thinkingStartedAtRef.current = Date.now();
    thinkingTimeoutRef.current = window.setTimeout(onTimeout, THINKING_STALL_TIMEOUT_MS);
  }

  function stopThinkingTimeout(): void {
    if (thinkingTimeoutRef.current !== null) {
      window.clearTimeout(thinkingTimeoutRef.current);
      thinkingTimeoutRef.current = null;
    }
    thinkingStartedAtRef.current = null;
  }

  async function ensureOutputContext(): Promise<AudioContext | null> {
    const AudioContextCtor = getAudioContextCtor();
    if (!AudioContextCtor) {
      return null;
    }
    if (!outputContextRef.current) {
      outputContextRef.current = new AudioContextCtor({ sampleRate: outputSampleRateRef.current });
    }
    await outputContextRef.current.resume();
    return outputContextRef.current;
  }

  function getPlaybackSchedule(
    context: AudioContext,
    chunkByteLength: number,
    reportedDuration: number,
  ): { startTime: number; nextPlaybackTime: number } {
    const currentTime = context.currentTime;
    const bufferDuration = Number.isFinite(reportedDuration) && reportedDuration > 0
      ? reportedDuration
      : chunkByteLength / 2 / context.sampleRate;
    let startTime = nextPlaybackTimeRef.current;

    if (startTime === 0) {
      playbackGapResetsRef.current += 1;
      lastPlaybackScheduleLagMsRef.current = 0;
      startTime = currentTime + PLAYBACK_SAFETY_BUFFER_SECONDS;
    } else if (startTime <= currentTime + PLAYBACK_SAFETY_BUFFER_SECONDS) {
      playbackGapResetsRef.current += 1;
      lastPlaybackScheduleLagMsRef.current = Math.max(
        0,
        Math.round((currentTime - startTime) * 1000),
      );
      startTime = currentTime + PLAYBACK_SAFETY_BUFFER_SECONDS;
    } else {
      lastPlaybackScheduleLagMsRef.current = 0;
    }

    return {
      startTime,
      nextPlaybackTime: startTime + bufferDuration,
    };
  }

  function buildClientDiagnostics(): Record<string, unknown> {
    const diagnostics: Record<string, unknown> = {
      browser: navigator.userAgent,
      init_phase: initPhaseRef.current,
      session_ready: sessionReadyRef.current,
    };
    if (lastAgentEventRef.current) {
      diagnostics.last_agent_event = lastAgentEventRef.current;
    }
    if (lastAgentErrorRef.current) {
      diagnostics.last_agent_error = lastAgentErrorRef.current;
    }
    if (thinkingStallMsRef.current !== null) {
      diagnostics.thinking_stall_ms = thinkingStallMsRef.current;
    }
    if (processorBufferSizeRef.current !== null) {
      diagnostics.processor_buffer_size = processorBufferSizeRef.current;
    }
    if (inputContextSampleRateRef.current !== null) {
      diagnostics.input_context_sample_rate = inputContextSampleRateRef.current;
    }
    if (inputChannelCountRef.current !== null) {
      diagnostics.input_channel_count = inputChannelCountRef.current;
    }
    if (trackSampleRateRef.current !== null) {
      diagnostics.track_sample_rate = trackSampleRateRef.current;
    }
    diagnostics.constraints_fallback_used = constraintsFallbackUsedRef.current;
    diagnostics.output_sample_rate = outputSampleRateRef.current;
    diagnostics.playback_gap_resets = playbackGapResetsRef.current;
    diagnostics.last_playback_schedule_lag_ms = lastPlaybackScheduleLagMsRef.current;
    return diagnostics;
  }

  async function cleanup(): Promise<void> {
    manualCloseRef.current = true;
    sessionReadyRef.current = false;
    stopInitTimeout();
    stopThinkingTimeout();
    stopKeepAlive();
    stopPlayback();
    processorRef.current?.disconnect();
    sourceNodeRef.current?.disconnect();
    muteGainRef.current?.disconnect();
    processorRef.current = null;
    sourceNodeRef.current = null;
    muteGainRef.current = null;
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    if (inputContextRef.current) {
      await inputContextRef.current.close();
      inputContextRef.current = null;
    }
    if (outputContextRef.current) {
      await outputContextRef.current.close();
      outputContextRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) {
      wsRef.current.close();
    }
    wsRef.current = null;
    setIsConnected(false);
    setIsListening(false);
    setIsThinking(false);
    setIsSpeaking(false);
  }

  return {
    error,
    isConnected,
    isListening,
    isThinking,
    isSpeaking,
    transcript,
    startSession,
    endSession,
  };
}

function createLowLatencyProcessor(context: AudioContext): ScriptProcessorNodeLike {
  for (const bufferSize of INPUT_BUFFER_SIZE_CANDIDATES) {
    try {
      return context.createScriptProcessor(bufferSize, 1, 1);
    } catch {
      continue;
    }
  }
  return context.createScriptProcessor(4096, 1, 1);
}
