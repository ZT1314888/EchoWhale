import { useEffect, useState } from "react";
import { MessagesSquare, Timer } from "lucide-react";

type SessionMeterProps = {
  /** 本轮已完成的开口轮数（由会话消息与实时转写共同派生） */
  turnCount: number;
};

function formatElapsed(seconds: number) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/** 本场计时 + 开口轮数。两个数字都来自真实状态，不预置目标值。 */
export function SessionMeter({ turnCount }: SessionMeterProps) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timerId = window.setInterval(() => setSeconds((current) => current + 1), 1000);
    return () => window.clearInterval(timerId);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3.5 py-2 font-mono text-[12px] font-bold tabular-nums">
        <Timer size={13} className="text-[#d8f34e]" aria-hidden="true" />
        {formatElapsed(seconds)}
      </span>
      <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3.5 py-2 text-[12px] font-bold">
        <MessagesSquare size={13} className="text-[#d8f34e]" aria-hidden="true" />
        {turnCount} 轮
      </span>
    </div>
  );
}
