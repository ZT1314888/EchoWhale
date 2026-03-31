import type { HistoryEntry } from "../data/mockSession";

import { HistoryItem } from "./HistoryItem";

export function HistoryRail({ entries }: { entries: HistoryEntry[] }) {
  return (
    <section className="panel-shell space-y-5" aria-label="History review">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Review lane</p>
          <h2 className="font-display text-3xl text-[var(--color-foam)]">History review</h2>
        </div>
        <button className="ghost-action" type="button">
          Open archive
        </button>
      </div>

      <div className="space-y-4">
        {entries.map((entry) => (
          <HistoryItem key={entry.id} entry={entry} />
        ))}
      </div>
    </section>
  );
}
