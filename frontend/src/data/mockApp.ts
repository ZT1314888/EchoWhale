import type { HistoryDetail, HistoryEntry, PracticeFeedback, SampleScene, SessionSummary } from "../types/app";

export const sampleScenes: SampleScene[] = [
  {
    id: "coffee",
    title: "咖啡店点单",
    body: "练习点饮料、回应店员，再把语气说得自然一些。",
    imageClass: "sample-scene--coffee",
    roleLabel: "角色 · 友好的店员",
    openingPrompt: "开场提示：店员先向你问好。先用一句简短英文回应，把对话顺利打开。",
    tags: ["点单菜单", "轻松语气"],
    liveHint: "先用更短的开场句，再把额外细节放到第二句里，会更稳。",
  },
  {
    id: "office",
    title: "办公室交流",
    body: "练习快速汇报状态、回应一个问题，并保持简洁。",
    imageClass: "sample-scene--office",
    roleLabel: "角色 · 项目同事",
    openingPrompt: "开场提示：同事先问你进度。先回答状态，再补一句下一步动作。",
    tags: ["简短汇报", "工作日常"],
    liveHint: "先说结果，再说原因，会更像真实办公室沟通。",
  },
  {
    id: "street",
    title: "街头问路",
    body: "练习问路、确认路线，再把关键地标清楚地重复出来。",
    imageClass: "sample-scene--street",
    roleLabel: "角色 · 路人",
    openingPrompt: "开场提示：先用一句英文礼貌发问，再补目的地信息。",
    tags: ["问路确认", "生活场景"],
    liveHint: "先说目的地，再问路线，会更容易得到清晰回复。",
  },
];

export const defaultFeedback: PracticeFeedback = {
  grammar: {
    title: "Grammar",
    body: "你的请求句式已经比较礼貌、清楚。继续把 “Could I get...” 放在开头，会更自然。",
  },
  moreNatural: {
    title: "More Natural",
    body: "在咖啡店里，先说饮品再补额外需求，会比一开始就把所有信息堆进去更顺。",
  },
  usefulWords: {
    title: "Useful Words",
    words: ["iced latte", "for here", "to go", "could I get", "anything else"],
    body: "把场景里反复出现的固定搭配记下来，下一轮会更快。",
  },
  nextStep: {
    title: "Next Step",
    body: "把同一个场景再练一轮，第二个问题回答得更快一点，不必解释太多。",
  },
};

export const baseSession: SessionSummary = {
  id: "session-coffee",
  title: "咖啡店柜台点单",
  roleLabel: "角色 · 友好的店员",
  openingPrompt: "开场提示：店员先向你问好。先用一句简短英文回应，把对话顺利打开。",
  tags: ["点单菜单", "轻松语气"],
  liveHint: "先用更短的开场句，再把额外细节放到第二句里，会更稳。",
  voiceTitle: "点一下，用声音回答",
  voiceBody: "文本输入仍然可用，但页面主动作始终是先开口再补充。",
  messages: [
    {
      id: "msg-coach-1",
      role: "coach",
      label: "教练 · 语音引导",
      content: "你好，今天想先点什么？先用一句简短英文把主需求说出来。",
    },
    {
      id: "msg-learner-1",
      role: "learner",
      label: "你 · 本轮回答",
      content: "Could I get an iced latte, please?",
    },
  ],
};

export const historyEntries: HistoryEntry[] = [
  {
    id: "session-coffee",
    practicedAt: "今天 09:20",
    status: "已完成 4 轮",
    sceneTitle: "咖啡店柜台点单",
    roleLabel: "店员对话",
    preview: "你已经能稳定用礼貌请求句开口，第二句补细节时仍有提速空间。",
    tags: ["餐饮", "礼貌表达"],
    reviewTitle: "本轮回响",
    reviewSummary: "主需求表达清楚，后续补充信息的节奏越来越自然。",
  },
  {
    id: "session-office",
    practicedAt: "昨天 20:15",
    status: "已完成 3 轮",
    sceneTitle: "办公室状态同步",
    roleLabel: "同事沟通",
    preview: "你能先给结果，再补原因，但结尾动作还可以更明确。",
    tags: ["工作", "简报"],
    reviewTitle: "复盘重点",
    reviewSummary: "先说进度结论会更像真实汇报，再用一句补行动项。",
  },
  {
    id: "session-street",
    practicedAt: "周一 18:42",
    status: "已完成 2 轮",
    sceneTitle: "街头问路确认路线",
    roleLabel: "路人问答",
    preview: "开场礼貌度不错，但复述地标时还可以更坚定一点。",
    tags: ["出行", "地标"],
    reviewTitle: "这轮收获",
    reviewSummary: "提问足够礼貌，接下来重点练路线确认的重复表达。",
  },
];

export const historyDetails: Record<string, HistoryDetail> = {
  "session-coffee": {
    entry: historyEntries[0],
    session: baseSession,
    review: {
      sessionId: "session-coffee",
      title: "本轮回响",
      highlight: "你先把主需求说清楚，再补细节，让整段交流听起来更顺，也更容易被理解。",
      nextTry: "先用短句开口，再追加杯型、温度或带走方式，会比一口气塞进长句更自然。",
      feedback: defaultFeedback,
    },
  },
  "session-office": {
    entry: historyEntries[1],
    session: {
      ...baseSession,
      id: "session-office",
      title: "办公室状态同步",
      roleLabel: "角色 · 项目同事",
      openingPrompt: "开场提示：同事先问你进度。先回答状态，再补一句下一步动作。",
      tags: ["简短汇报", "工作日常"],
      liveHint: "先说结果，再说原因，会更像真实办公室沟通。",
      messages: [
        {
          id: "office-coach-1",
          role: "coach",
          label: "教练 · 语音引导",
          content: "How is the feature going? Give me the current status first.",
        },
        {
          id: "office-learner-1",
          role: "learner",
          label: "你 · 本轮回答",
          content: "It's almost ready, and I'm checking the final details now.",
        },
      ],
    },
    review: {
      sessionId: "session-office",
      title: "复盘重点",
      highlight: "你已经能先给进度结论，这让句子更像真实同步。",
      nextTry: "下一轮试着把时间承诺说得更明确，例如 by this afternoon。",
      feedback: defaultFeedback,
    },
  },
  "session-street": {
    entry: historyEntries[2],
    session: {
      ...baseSession,
      id: "session-street",
      title: "街头问路确认路线",
      roleLabel: "角色 · 热心路人",
      openingPrompt: "开场提示：先礼貌提问，再确认目的地和地标。",
      tags: ["问路确认", "生活场景"],
      liveHint: "问路时先说目的地，再确认转弯位置，会更清楚。",
      messages: [
        {
          id: "street-coach-1",
          role: "coach",
          label: "教练 · 语音引导",
          content: "Excuse me, where do you need to go? Ask politely first.",
        },
        {
          id: "street-learner-1",
          role: "learner",
          label: "你 · 本轮回答",
          content: "Excuse me, could you tell me how to get to the station?",
        },
      ],
    },
    review: {
      sessionId: "session-street",
      title: "这轮收获",
      highlight: "你的开场很礼貌，已经建立起真实生活场景的语气。",
      nextTry: "下一轮把地标和转弯方向再复述一次，会更像真实确认路线。",
      feedback: defaultFeedback,
    },
  },
};
