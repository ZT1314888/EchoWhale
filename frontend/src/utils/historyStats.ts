import type { HistoryEntry } from "../types/app";

export type HistoryFilter = "all" | "completed" | "active";
export type HistorySort = "newest" | "oldest";

/** 列表里已加载的那部分条目的口径统计：Sessions/Released 是真实值，其余后端无字段。 */
export type HistoryStats = {
  loadedSessions: number;
  completedSessions: number;
};

export function summarizeHistory(entries: HistoryEntry[]): HistoryStats {
  return {
    loadedSessions: entries.length,
    completedSessions: entries.filter((entry) => isCompleted(entry)).length,
  };
}

/** 后端 `_format_status` 对已完成的会话一律以「已完成」开头（带轮数时是「已完成 N 轮」）。 */
export function isCompleted(entry: HistoryEntry): boolean {
  return entry.status.startsWith("已完成");
}

export function filterHistory(entries: HistoryEntry[], filter: HistoryFilter): HistoryEntry[] {
  if (filter === "all") {
    return entries;
  }
  if (filter === "completed") {
    return entries.filter((entry) => isCompleted(entry));
  }
  return entries.filter((entry) => !isCompleted(entry));
}

/** 只搜真实存在的字段；命中大小写不敏感的标题、角色或标签。 */
export function searchHistory(entries: HistoryEntry[], keyword: string): HistoryEntry[] {
  const needle = keyword.trim().toLowerCase();
  if (!needle) {
    return entries;
  }
  return entries.filter((entry) =>
    [entry.sceneTitle, entry.roleLabel, ...entry.tags].some((field) => field.toLowerCase().includes(needle)),
  );
}

/**
 * 按练习时间排序。`practicedAt` 是后端格式化的 `YYYY-MM-DD HH:MM`，字符串序即时间序；
 * 解析不出来的条目一律排在末尾（两个方向上都是），不用 `new Date()` 造一个假时间。
 */
export function sortHistory(entries: HistoryEntry[], sort: HistorySort): HistoryEntry[] {
  const direction = sort === "newest" ? -1 : 1;

  return [...entries].sort((left, right) => {
    const leftKey = toSortKey(left.practicedAt);
    const rightKey = toSortKey(right.practicedAt);

    if (leftKey === null || rightKey === null) {
      if (leftKey === rightKey) {
        return 0;
      }
      return leftKey === null ? 1 : -1;
    }

    if (leftKey === rightKey) {
      return 0;
    }
    return leftKey < rightKey ? -direction : direction;
  });
}

const PRACTICED_AT_PATTERN = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

function toSortKey(practicedAt: string): string | null {
  return PRACTICED_AT_PATTERN.test(practicedAt) ? practicedAt : null;
}
