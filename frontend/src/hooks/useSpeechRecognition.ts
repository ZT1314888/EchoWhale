import { useEffect, useMemo, useRef, useState } from "react";

type SpeechRecognitionAlternativeLike = {
  transcript?: string;
};

type SpeechRecognitionResultLike = ArrayLike<SpeechRecognitionAlternativeLike> & {
  isFinal?: boolean;
};

type SpeechRecognitionEventLike = {
  resultIndex?: number;
  results?: ArrayLike<SpeechRecognitionResultLike>;
};

type SpeechRecognitionErrorEventLike = {
  error?: string;
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionCtor = new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionCtor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionCtor;
  }
}

function normalizeTranscript(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function mapSpeechError(error?: string): string {
  switch (error) {
    case "not-allowed":
    case "service-not-allowed":
      return "麦克风权限未开启，请允许浏览器访问麦克风后重试。";
    case "audio-capture":
      return "没有检测到可用麦克风，请检查设备后重试。";
    case "network":
      return "语音识别服务暂时不可用，请稍后再试。";
    case "no-speech":
      return "没有识别到有效语音，请再说一句。";
    default:
      return "语音识别暂时不可用，请稍后再试。";
  }
}

export function useSpeechRecognition(language = "en-US") {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const finalTranscriptRef = useRef("");
  const [transcript, setTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState("");

  const RecognitionCtor = useMemo(
    () => window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null,
    [],
  );
  const isSupported = RecognitionCtor !== null;

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  function resetTranscript() {
    finalTranscriptRef.current = "";
    setTranscript("");
  }

  function startListening() {
    if (!RecognitionCtor) {
      setError("当前浏览器不支持语音识别，请改用支持 Web Speech API 的浏览器。");
      return false;
    }

    const recognition = new RecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = language;
    recognition.onresult = (event) => {
      const results = event.results ?? [];
      const finalParts: string[] = [];
      const interimParts: string[] = [];

      for (let index = 0; index < results.length; index += 1) {
        const result = results[index];
        const fragment = normalizeTranscript(result?.[0]?.transcript ?? "");

        if (!fragment) {
          continue;
        }

        if (result?.isFinal) {
          finalParts.push(fragment);
        } else {
          interimParts.push(fragment);
        }
      }

      const nextFinal = normalizeTranscript(finalParts.join(" "));
      finalTranscriptRef.current = nextFinal;
      setTranscript(normalizeTranscript(`${nextFinal} ${interimParts.join(" ")}`));
    };
    recognition.onerror = (event) => {
      setError(mapSpeechError(event.error));
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
    };

    resetTranscript();
    setError("");
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setIsListening(true);
      return true;
    } catch {
      setError("麦克风暂时无法启动，请稍后再试。");
      return false;
    }
  }

  function stopListening() {
    recognitionRef.current?.stop();
  }

  return {
    error,
    isListening,
    isSupported,
    startListening,
    stopListening,
    transcript,
  };
}
