import type { HistoryEntry } from "../data/mockSession";

export function HistoryItem({ entry }: { entry: HistoryEntry }) {
  return (
    <article className="space-y-3 rounded-[24px] border border-white/10 bg-black/10 p-4 transition hover:border-[var(--color-aqua)]/30 hover:bg-white/5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[var(--color-foam)]">{entry.scene}</p>
          <p className="mt-1 text-xs uppercase tracking-[0.22em] text-white/35">{entry.role}</p>
        </div>
        <span className="signal-chip">{entry.score}</span>
      </div>
      <p className="text-sm leading-7 text-[var(--color-mist)]">{entry.preview}</p>
      <p className="text-xs uppercase tracking-[0.22em] text-white/30">{entry.updatedAt}</p>
    </article>
  );
}
