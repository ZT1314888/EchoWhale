import { useId } from "react";

export function Logo({
  className = "h-10 w-10",
  title = "EchoWhale logo",
  ...props
}) {
  const gradientSeed = useId().replace(/:/g, "");
  const whaleBodyId = `whaleBody-${gradientSeed}`;
  const echoWaveId = `echoWave-${gradientSeed}`;

  return (
    <svg
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-hidden={title ? undefined : true}
      aria-label={title || undefined}
      {...props}
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
      <title>{title}</title>
      <path
        d="M 88 58 Q 100 48 112 58"
        data-wave="short"
        fill="none"
        stroke={`url(#${echoWaveId})`}
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d="M 76 44 Q 100 28 124 44"
        data-wave="mid"
        fill="none"
        stroke={`url(#${echoWaveId})`}
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d="M 64 30 Q 100 6 136 30"
        data-wave="long"
        fill="none"
        stroke={`url(#${echoWaveId})`}
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d="M 40 110 C 40 70, 80 70, 100 70 C 130 70, 150 90, 150 110 Q 165 105, 175 100 Q 170 120, 150 125 C 100 140, 50 130, 40 110 Z"
        data-whale-body="true"
        fill={`url(#${whaleBodyId})`}
      />
      <circle cx="65" cy="95" r="5" fill="#FFFFFF" data-whale-eye="true" />
    </svg>
  );
}
