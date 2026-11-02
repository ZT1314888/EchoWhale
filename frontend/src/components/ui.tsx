import type { ReactNode } from "react";

/* ---------- layout ---------- */

export function PageShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={`mx-auto w-full ${wide ? "max-w-7xl" : "max-w-5xl"} px-4 py-8 sm:px-6`}>{children}</div>;
}

export function Eyebrow({ children, dark }: { children: ReactNode; dark?: boolean }) {
  return (
    <p
      className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] ${
        dark ? "border-white/20 bg-white/10 text-white/80" : "border-[#131311]/12 bg-white/70 text-stone-600"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-[#4f46e5]" />
      {children}
    </p>
  );
}

export function SectionTitle({ en, cn, desc, dark }: { en: string; cn: string; desc?: string; dark?: boolean }) {
  return (
    <div className="max-w-2xl">
      <h2 className={`font-display text-[26px] font-bold leading-tight tracking-tight sm:text-[32px] ${dark ? "text-white" : "text-[#131311]"}`}>
        {en}
        <span className={`font-serif-accent ml-2 align-middle text-[0.62em] font-medium ${dark ? "text-white/50" : "text-stone-400"}`}>{cn}</span>
      </h2>
      {desc && <p className={`mt-2 text-[13.5px] leading-relaxed ${dark ? "text-white/55" : "text-stone-500"}`}>{desc}</p>}
    </div>
  );
}

/* ---------- scores ---------- */

function scoreColor(score: number) {
  if (score >= 85) return "#059669";
  if (score >= 70) return "#4f46e5";
  if (score >= 55) return "#d97706";
  return "#e11d48";
}

export function ScoreRing({
  score,
  size = 120,
  stroke = 10,
  label,
  dark,
}: {
  score: number;
  size?: number;
  stroke?: number;
  label?: string;
  dark?: boolean;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const color = scoreColor(score);
  return (
    <div className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={dark ? "rgba(255,255,255,0.14)" : "#e8e6e0"} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * pct) / 100}
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="absolute text-center">
        <div className={`font-display font-bold ${dark ? "text-white" : "text-[#131311]"}`} style={{ fontSize: size * 0.25 }}>
          {score}
        </div>
        {label && <div className={`text-[10.5px] font-semibold ${dark ? "text-white/50" : "text-stone-400"}`}>{label}</div>}
      </div>
    </div>
  );
}

export function ScoreBar({ label, cn, score, delay = 0 }: { label: string; cn: string; score: number; delay?: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-[13px] font-bold text-[#131311]">
          {label} <span className="ml-1 text-[11px] font-normal text-stone-400">{cn}</span>
        </p>
        <p className="font-display text-[15px] font-bold">{score}</p>
      </div>
      <div className="mt-1.5 h-[7px] overflow-hidden rounded-full bg-[#131311]/8">
        <div
          className="h-full rounded-full bg-[#131311]"
          style={{ width: `${score}%`, transition: "width 1.1s cubic-bezier(0.22,1,0.36,1)", transitionDelay: `${delay}ms` }}
        />
      </div>
    </div>
  );
}

export function RadarChart({ scores, dark }: { scores: { label: string; value: number }[]; dark?: boolean }) {
  const size = 224;
  const cx = size / 2;
  const cy = size / 2;
  const R = 78;
  const n = scores.length;
  const point = (i: number, v: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const r = (R * v) / 100;
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  };
  const polygon = scores.map((s, i) => point(i, s.value).join(",")).join(" ");
  const rings = [25, 50, 75, 100].map((v) => scores.map((_, i) => point(i, v).join(",")).join(" "));
  const grid = dark ? "rgba(255,255,255,0.14)" : "#e4e2db";

  return (
    <svg width={size} height={size} className="mx-auto" role="img" aria-label="能力雷达图">
      {rings.map((r, i) => (
        <polygon
          key={i}
          points={r}
          fill={i === 3 ? (dark ? "rgba(255,255,255,0.03)" : "rgba(19,19,17,0.02)") : "none"}
          stroke={grid}
          strokeWidth="1"
        />
      ))}
      {scores.map((s, i) => {
        const [x, y] = point(i, 100);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke={grid} strokeWidth="1" />;
      })}
      <polygon points={polygon} fill="rgba(79,70,229,0.14)" stroke="#4f46e5" strokeWidth="2.5" strokeLinejoin="round" />
      {scores.map((s, i) => {
        const [x, y] = point(i, s.value);
        return <circle key={i} cx={x} cy={y} r="4" fill="#131311" stroke="#fff" strokeWidth="2" />;
      })}
      {scores.map((s, i) => {
        const [x, y] = point(i, 120);
        return (
          <text
            key={i}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="10.5"
            fontWeight="700"
            fill={dark ? "rgba(255,255,255,0.65)" : "#78716c"}
          >
            {s.label}
          </text>
        );
      })}
    </svg>
  );
}

/* ---------- misc ---------- */

export function Stat({ value, label, sub }: { value: string; label: string; sub?: string }) {
  return (
    <div className="rounded-3xl border border-[#131311]/8 bg-white p-5">
      <p className="font-display text-[26px] font-bold tracking-tight">{value}</p>
      <p className="mt-0.5 text-[12px] font-semibold text-stone-500">{label}</p>
      {sub && <p className="text-[11px] text-stone-400">{sub}</p>}
    </div>
  );
}

export function EmptyState({ icon, title, desc, action }: { icon: ReactNode; title: string; desc: string; action?: ReactNode }) {
  return (
    <div className="rounded-[28px] border border-dashed border-[#131311]/15 bg-white/60 p-14 text-center">
      <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">{icon}</div>
      <p className="font-display mt-5 text-xl font-bold">{title}</p>
      <p className="mx-auto mt-1.5 max-w-sm text-[13.5px] leading-relaxed text-stone-500">{desc}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
