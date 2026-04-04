import { useId } from "react";

type AnalysisStage = "scene" | "role" | "ready";

type StartupAnalysisOrbProps = {
  stage: AnalysisStage;
  isComplete: boolean;
  className?: string;
};

export function StartupAnalysisOrb({
  stage,
  isComplete,
  className = "",
}: StartupAnalysisOrbProps) {
  const gradientSeed = useId().replace(/:/g, "");
  const whaleBodyId = `startup-whale-body-${gradientSeed}`;
  const echoWaveId = `startup-echo-wave-${gradientSeed}`;

  return (
    <div
      className={`startup-analysis-orb ${className}`.trim()}
      data-stage={stage}
      data-complete={isComplete}
      aria-hidden="true"
    >
      <span className="startup-analysis-ring startup-analysis-ring--pulse-1" />
      <span className="startup-analysis-ring startup-analysis-ring--pulse-2" />
      <span className="startup-analysis-ring startup-analysis-ring--pulse-3" />
      <span className="startup-analysis-core" />

      <svg
        viewBox="0 0 200 200"
        xmlns="http://www.w3.org/2000/svg"
        className="startup-analysis-logo"
        role="presentation"
      >
        <defs>
          <linearGradient id={whaleBodyId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#32ADE6" />
            <stop offset="100%" stopColor="#0A84FF" />
          </linearGradient>
          <linearGradient id={echoWaveId} x1="0%" y1="100%" x2="0%" y2="0%">
            <stop offset="0%" stopColor="#0A84FF" />
            <stop offset="100%" stopColor="#30D158" />
          </linearGradient>
        </defs>

        <path
          className="startup-analysis-echo startup-analysis-echo--short"
          d="M 88 58 Q 100 48 112 58"
          pathLength="100"
          fill="none"
          stroke={`url(#${echoWaveId})`}
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          className="startup-analysis-echo startup-analysis-echo--mid"
          d="M 76 44 Q 100 28 124 44"
          pathLength="100"
          fill="none"
          stroke={`url(#${echoWaveId})`}
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          className="startup-analysis-echo startup-analysis-echo--long"
          d="M 64 30 Q 100 6 136 30"
          pathLength="100"
          fill="none"
          stroke={`url(#${echoWaveId})`}
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M 40 110 C 40 70, 80 70, 100 70 C 130 70, 150 90, 150 110 Q 165 105, 175 100 Q 170 120, 150 125 C 100 140, 50 130, 40 110 Z"
          fill={`url(#${whaleBodyId})`}
        />
        <circle cx="65" cy="95" r="5" fill="#FFFFFF" />
      </svg>
    </div>
  );
}

export type { AnalysisStage };
