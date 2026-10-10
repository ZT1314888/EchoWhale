import { Logo } from "./Logo";

type AnalysisStage = "scene" | "role" | "ready";

type StartupAnalysisOrbProps = {
  stage: AnalysisStage;
  isComplete: boolean;
  className?: string;
};

const RING_WIDTHS = ["w-[48%]", "w-[66%]", "w-[84%]"];
const RING_DELAYS = [0, 1.1, 2.2];

/**
 * 分析等待页的中心视觉：三圈 iris 脉冲 + 白底鲸鱼标。
 *
 * 配色从旧的蓝色系换到新设计语言的 iris（#4f46e5）/ lime（#d8f34e），
 * 但仍是纯装饰，整块 aria-hidden —— 真实进度由旁边的阶段卡片与百分比承担。
 */
export function StartupAnalysisOrb({ stage, isComplete, className = "" }: StartupAnalysisOrbProps) {
  return (
    <div
      className={`relative grid aspect-square w-[min(100%,360px)] place-items-center ${className}`.trim()}
      data-stage={stage}
      data-complete={isComplete}
      aria-hidden="true"
    >
      {RING_WIDTHS.map((width, index) => (
        <span
          key={width}
          className={`absolute ${width} aspect-square rounded-full border border-[#4f46e5]/30 animate-pulse-ring`}
          style={{ animationDelay: `${RING_DELAYS[index]}s` }}
        />
      ))}

      <span className="relative grid aspect-square w-[34%] place-items-center rounded-full bg-[#131311] shadow-[0_24px_54px_-12px_rgba(79,70,229,0.45)]">
        <span className="absolute inset-0 rounded-full bg-gradient-to-br from-[#4f46e5]/40 to-[#d8f34e]/25 blur-md" />
        <Logo className="relative h-1/2 w-1/2" title="" />
      </span>

      {/* 完成时收束成实心 lime 圈，与进行中的扩散脉冲形成对比。 */}
      {isComplete ? (
        <span className="absolute inset-0 grid place-items-center">
          <span className="h-[34%] w-[34%] rounded-full ring-2 ring-[#d8f34e]/70" />
        </span>
      ) : null}

    </div>
  );
}

export type { AnalysisStage };
