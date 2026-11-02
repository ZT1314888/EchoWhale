import { describe, expect, it } from "vitest";

import { CEFR_LEVELS, buildMedals, cefrLevelIndex, countEarnedMedals, toCefrDisplay } from "./progressStats";

describe("cefrLevelIndex", () => {
  it("returns -1 when the backend has not estimated a level yet", () => {
    expect(cefrLevelIndex(null)).toBe(-1);
  });

  it("maps every published level to its slot", () => {
    expect(CEFR_LEVELS.map((level) => cefrLevelIndex(level))).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("returns -1 for a level outside the published set", () => {
    expect(cefrLevelIndex("D9")).toBe(-1);
  });
});

describe("toCefrDisplay", () => {
  it("renders the Chinese label alongside the raw level", () => {
    expect(toCefrDisplay("B1")).toBe("进阶（B1）");
    expect(toCefrDisplay("C2")).toBe("精通（C2）");
  });

  it("falls back to the raw value for an unknown level instead of inventing a label", () => {
    expect(toCefrDisplay("D9")).toBe("D9（D9）");
  });
});

describe("buildMedals", () => {
  it("locks every medal for a learner who has never spoken", () => {
    const medals = buildMedals(0);

    expect(medals).toHaveLength(6);
    expect(countEarnedMedals(medals)).toBe(0);
    expect(medals[0].requirement).toBe("至少 1 轮");
  });

  it("earns 首次开口 from the first turn and 十轮练习 at ten", () => {
    expect(countEarnedMedals(buildMedals(1))).toBe(1);
    expect(countEarnedMedals(buildMedals(9))).toBe(1);
    expect(countEarnedMedals(buildMedals(10))).toBe(2);
    expect(countEarnedMedals(buildMedals(250))).toBe(2);
  });

  it("keeps the four medals the backend cannot back locked at any turn count", () => {
    const unbacked = buildMedals(9_999).filter((medal) =>
      ["streak", "wordsmith", "high-score", "daily-goal"].includes(medal.id),
    );

    expect(unbacked).toHaveLength(4);
    expect(unbacked.every((medal) => !medal.earned)).toBe(true);
    expect(unbacked.map((medal) => medal.requirement)).toEqual([
      "需要连击字段",
      "需要词数字段",
      "需要评分字段",
      "需要目标字段",
    ]);
  });
});
