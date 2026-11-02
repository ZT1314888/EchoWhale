import type { HistoryEntry } from "../types/app";
import { isCompleted } from "../utils/historyStats";

type HistoryListProps = {
  entries: HistoryEntry[];
  activeId: string;
  onSelect: (sessionId: string) => void;
};

/** 历史列表：只展示真实字段（时间/状态/标题/预览/标签），不出现分数位。 */
export function HistoryList({ entries, activeId, onSelect }: HistoryListProps) {
  return (
    <ul className="space-y-2.5" aria-label="历史会话列表">
      {entries.map((entry) => {
        const active = entry.id === activeId;
        const done = isCompleted(entry);

        return (
          <li key={entry.id}>
            <button
              type="button"
              onClick={() => onSelect(entry.id)}
              aria-current={active ? "true" : undefined}
              className={`w-full rounded-[24px] border p-4 text-left transition ${
                active
                  ? "border-[#131311] bg-white shadow-[0_18px_36px_-24px_rgba(19,19,17,0.4)]"
                  : "border-[#131311]/8 bg-white hover:border-[#131311]/30"
              }`}
            >
              <span className="flex items-center gap-2 font-mono text-[10.5px] font-bold uppercase tracking-[0.16em] text-stone-400">
                {entry.practicedAt}
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    done ? "bg-emerald-500/10 text-emerald-600" : "bg-stone-100 text-stone-500"
                  }`}
                >
                  {entry.status}
                </span>
              </span>
              <span className="font-display mt-1.5 block truncate text-[16px] font-bold tracking-tight">
                {entry.sceneTitle}
              </span>
              <span className="mt-0.5 block text-[12px] text-stone-400">{entry.roleLabel}</span>
              <span className="mt-1.5 line-clamp-2 block text-[12.5px] leading-relaxed text-stone-500">
                {entry.preview}
              </span>
              {entry.tags.length ? (
                <span className="mt-2.5 flex flex-wrap gap-1.5">
                  {entry.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-stone-100 px-2.5 py-0.5 text-[10.5px] font-semibold text-stone-500"
                    >
                      {tag}
                    </span>
                  ))}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
