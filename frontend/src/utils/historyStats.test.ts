import { describe, expect, it } from "vitest";

import type { HistoryEntry } from "../types/app";
import { filterHistory, isCompleted, searchHistory, sortHistory, summarizeHistory } from "./historyStats";

function entry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id: "sess_1",
    practicedAt: "2026-04-04 15:20",
    status: "已完成 1 轮",
    sceneTitle: "咖啡店柜台点单",
    roleLabel: "店员对话",
    preview: "你已经说清楚主要需求。",
    tags: ["coffee", "menu"],
    reviewTitle: "本轮回响",
    reviewSummary: "下一轮再补一条细节。",
    ...overrides,
  };
}

describe("summarizeHistory", () => {
  it("counts only what the loaded page actually contains", () => {
    const stats = summarizeHistory([
      entry({ id: "a", status: "已完成 3 轮" }),
      entry({ id: "b", status: "进行中" }),
      entry({ id: "c", status: "已完成" }),
    ]);

    expect(stats).toEqual({ loadedSessions: 3, completedSessions: 2 });
  });

  it("reports zeroes for an empty list rather than pretending to know a total", () => {
    expect(summarizeHistory([])).toEqual({ loadedSessions: 0, completedSessions: 0 });
  });
});

describe("isCompleted", () => {
  it("treats both the bare and numbered completion labels as completed", () => {
    expect(isCompleted(entry({ status: "已完成" }))).toBe(true);
    expect(isCompleted(entry({ status: "已完成 12 轮" }))).toBe(true);
  });

  it("treats an in-progress session as not completed", () => {
    expect(isCompleted(entry({ status: "进行中" }))).toBe(false);
  });
});

describe("filterHistory", () => {
  const entries = [entry({ id: "a", status: "已完成 2 轮" }), entry({ id: "b", status: "进行中" })];

  it("returns everything for the all filter", () => {
    expect(filterHistory(entries, "all")).toHaveLength(2);
  });

  it("keeps only completed sessions", () => {
    expect(filterHistory(entries, "completed").map((item) => item.id)).toEqual(["a"]);
  });

  it("keeps only unfinished sessions", () => {
    expect(filterHistory(entries, "active").map((item) => item.id)).toEqual(["b"]);
  });
});

describe("searchHistory", () => {
  const entries = [
    entry({ id: "a", sceneTitle: "咖啡店柜台点单", tags: ["coffee"] }),
    entry({ id: "b", sceneTitle: "办公室周会", roleLabel: "角色 · manager", tags: ["meeting"] }),
  ];

  it("returns everything for a blank keyword", () => {
    expect(searchHistory(entries, "   ")).toHaveLength(2);
  });

  it("matches the scene title, the role label and the tags case-insensitively", () => {
    expect(searchHistory(entries, "咖啡").map((item) => item.id)).toEqual(["a"]);
    expect(searchHistory(entries, "MANAGER").map((item) => item.id)).toEqual(["b"]);
    expect(searchHistory(entries, "coffee").map((item) => item.id)).toEqual(["a"]);
  });

  it("returns nothing when no field matches", () => {
    expect(searchHistory(entries, "机场")).toEqual([]);
  });
});

describe("sortHistory", () => {
  const entries = [
    entry({ id: "mid", practicedAt: "2026-04-04 15:20" }),
    entry({ id: "old", practicedAt: "2026-01-02 09:00" }),
    entry({ id: "new", practicedAt: "2026-09-30 23:59" }),
  ];

  it("orders newest first", () => {
    expect(sortHistory(entries, "newest").map((item) => item.id)).toEqual(["new", "mid", "old"]);
  });

  it("orders oldest first", () => {
    expect(sortHistory(entries, "oldest").map((item) => item.id)).toEqual(["old", "mid", "new"]);
  });

  it("pushes unparseable timestamps to the end instead of inventing a date", () => {
    const messy = [entry({ id: "bad", practicedAt: "昨天" }), entry({ id: "ok", practicedAt: "2026-04-04 15:20" })];

    expect(sortHistory(messy, "newest").map((item) => item.id)).toEqual(["ok", "bad"]);
    expect(sortHistory(messy, "oldest").map((item) => item.id)).toEqual(["ok", "bad"]);
  });

  it("keeps equal timestamps in place in both directions", () => {
    const tied = [entry({ id: "a", practicedAt: "2026-04-04 15:20" }), entry({ id: "b", practicedAt: "2026-04-04 15:20" })];

    expect(sortHistory(tied, "newest").map((item) => item.id)).toEqual(["a", "b"]);
    expect(sortHistory(tied, "oldest").map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("leaves an all-unparseable list untouched and does not mutate the input", () => {
    const input = [...entries];
    const messy = [entry({ id: "x", practicedAt: "-" }), entry({ id: "y", practicedAt: "不详" })];

    expect(sortHistory(messy, "newest").map((item) => item.id)).toEqual(["x", "y"]);
    expect(sortHistory(messy, "oldest").map((item) => item.id)).toEqual(["x", "y"]);

    sortHistory(input, "oldest");
    expect(input.map((item) => item.id)).toEqual(["mid", "old", "new"]);
  });
});
