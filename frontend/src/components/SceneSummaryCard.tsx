import type { SessionModel } from "../data/mockSession";

const formatConfidence = (confidence: number) => `${Math.round(confidence * 100)}% aligned`;

export function SceneSummaryCard({ session }: { session: SessionModel }) {
  return (
    <section className="panel-shell space-y-5" aria-label="Scene summary">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Live scene</p>
          <h2 className="font-display text-2xl text-[var(--color-foam)]">{session.scene}</h2>
        </div>
        <span className="signal-chip signal-chip--warm">{formatConfidence(session.confidence)}</span>
      </div>

      <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
        <p className="eyebrow">Role</p>
        <p className="mt-2 text-lg font-semibold text-[var(--color-foam)]">{session.role}</p>
        <p className="mt-3 text-sm leading-7 text-[var(--color-mist)]">{session.opener}</p>
      </div>

      <div>
        <p className="eyebrow">Signal tags</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {session.labels.map((label) => (
            <span key={label} className="tag-chip">
              {label}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-[24px] border border-dashed border-white/15 bg-black/10 px-4 py-3 text-sm text-[var(--color-mist)]">
        Current media source: <span className="text-[var(--color-foam)]">{session.mediaTitle}</span>
      </div>
    </section>
  );
}
