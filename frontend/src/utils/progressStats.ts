export const CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;

export type CefrLevel = (typeof CEFR_LEVELS)[number];

// CEFR 等级是服务端下发的封闭集合值（A1..C2），中文文案映射归前端展示。
const CEFR_LEVEL_LABELS: Record<string, string> = {
  A1: "入门",
  A2: "基础",
  B1: "进阶",
  B2: "中高",
  C1: "高级",
  C2: "精通",
};

/** `null` 表示后端还没给出估计，此时不点亮任何等级段。 */
export function cefrLevelIndex(cefrEstimate: string | null): number {
  if (!cefrEstimate) {
    return -1;
  }
  return CEFR_LEVELS.indexOf(cefrEstimate as CefrLevel);
}

export function toCefrDisplay(cefrEstimate: string): string {
  return `${CEFR_LEVEL_LABELS[cefrEstimate] ?? cefrEstimate}（${cefrEstimate}）`;
}

export type Medal = {
  id: string;
  title: string;
  desc: string;
  /** 已达成 */
  earned: boolean;
  /** 未达成时展示的解锁条件 */
  requirement: string;
};

/**
 * 成就徽章。只有两个条件能由现有接口判定（`practicedTurnCount`），其余四个后端没有
 * 对应字段（连击天数、词数、平均分、每日目标），**永久锁定并如实显示所需字段**，
 * 而不是按编造的数字点亮。
 */
export function buildMedals(practicedTurnCount: number): Medal[] {
  return [
    {
      id: "first-turn",
      title: "首次开口",
      desc: "完成第一轮练习",
      earned: practicedTurnCount >= 1,
      requirement: "至少 1 轮",
    },
    {
      id: "ten-turns",
      title: "十轮练习",
      desc: "累计完成 10 轮开口",
      earned: practicedTurnCount >= 10,
      requirement: "至少 10 轮",
    },
    {
      id: "streak",
      title: "连续打卡",
      desc: "后端暂未提供连续练习天数",
      earned: false,
      requirement: "需要连击字段",
    },
    {
      id: "wordsmith",
      title: "词汇匠人",
      desc: "后端暂未提供累计词数",
      earned: false,
      requirement: "需要词数字段",
    },
    {
      id: "high-score",
      title: "高分场次",
      desc: "后端暂未提供评分",
      earned: false,
      requirement: "需要评分字段",
    },
    {
      id: "daily-goal",
      title: "今日目标",
      desc: "后端暂未提供每日目标",
      earned: false,
      requirement: "需要目标字段",
    },
  ];
}

export function countEarnedMedals(medals: Medal[]): number {
  return medals.filter((medal) => medal.earned).length;
}
