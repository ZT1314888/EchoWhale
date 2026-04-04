import type { HistoryEntry } from "../types/app";

type HistoryListProps = {
  entries: HistoryEntry[];
  activeId: string;
  onSelect: (sessionId: string) => void;
};

export function HistoryList({ entries, activeId, onSelect }: HistoryListProps) {
  return (
    <ul className="history-list" aria-label="历史会话列表">
      {entries.map((entry) => {
        const active = entry.id === activeId;

        return (
          <li key={entry.id}>
            <button
              className={active ? "history-row history-row--active" : "history-row"}
              type="button"
              onClick={() => onSelect(entry.id)}
            >
              <span className="history-row-top">
                <span className="history-row-time">{entry.practicedAt}</span>
                <span className="history-row-status">{entry.status}</span>
              </span>
              <span className="history-row-title">{entry.sceneTitle}</span>
              <span className="history-row-preview">{entry.preview}</span>
              <span className="pill-row">
                {entry.tags.map((tag) => (
                  <span key={tag} className="info-pill">
                    {tag}
                  </span>
                ))}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
