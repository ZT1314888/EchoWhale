import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 浏览器 TTS 跟读。`supported` 为 false 时调用方应隐藏跟读入口，
 * 而不是渲染一个点了没反应的按钮。
 */
export function useSpeechSynthesis() {
  // 在渲染期把对象取出来存好：jsdom / 老浏览器可能根本没有 speechSynthesis，
  // 卸载清理时再读一次 window 会拿到 undefined。
  const synth = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
  const supported = synth !== null;
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const finish = useCallback(() => {
    utteranceRef.current = null;
    setSpeaking(false);
  }, []);

  const cancel = useCallback(() => {
    synth?.cancel();
    finish();
  }, [synth, finish]);

  const speak = useCallback(
    (text: string) => {
      if (!synth || !text.trim()) {
        return;
      }
      synth.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";
      utterance.rate = 0.95;
      utterance.onend = finish;
      utterance.onerror = finish;
      utteranceRef.current = utterance;
      setSpeaking(true);
      synth.speak(utterance);
    },
    [synth, finish],
  );

  useEffect(() => {
    return () => {
      synth?.cancel();
    };
  }, [synth]);

  return { supported, speaking, speak, cancel };
}
