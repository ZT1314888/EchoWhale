import { Square, Volume2 } from "lucide-react";

import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";

type SpeakButtonProps = {
  text: string;
  /** 是否处于播放态；由调用方决定文案，默认「跟读」 */
  compact?: boolean;
};

/**
 * 跟读按钮：点一次朗读，再点一次停下。浏览器不支持语音合成时整个按钮不渲染 ——
 * 一个永远没反应的按钮比没有按钮更糟。
 */
export function SpeakButton({ text, compact = false }: SpeakButtonProps) {
  const { supported, speaking, speak, cancel } = useSpeechSynthesis();

  if (!supported) {
    return null;
  }

  const active = speaking;

  return (
    <button
      type="button"
      onClick={() => (active ? cancel() : speak(text))}
      aria-label={active ? `停止跟读：${text}` : `跟读：${text}`}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-bold transition ${
        active
          ? "bg-[#131311] text-[#d8f34e]"
          : "bg-stone-100 text-stone-600 hover:bg-[#131311] hover:text-[#d8f34e]"
      } ${compact ? "" : "mt-2.5"}`}
    >
      {active ? <Square size={12} className="fill-current" aria-hidden="true" /> : <Volume2 size={13} aria-hidden="true" />}
      跟读
    </button>
  );
}
