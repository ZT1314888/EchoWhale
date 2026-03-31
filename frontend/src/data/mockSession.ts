export type FeedbackModel = {
  grammar: string;
  moreNatural: string;
  usefulWords: string[];
};

export type MessageModel = {
  id: string;
  role: "coach" | "learner";
  text: string;
  feedback?: FeedbackModel;
};

export type SessionModel = {
  scene: string;
  role: string;
  opener: string;
  confidence: number;
  labels: string[];
  mediaTitle: string;
  messages: MessageModel[];
};

export type HistoryEntry = {
  id: string;
  scene: string;
  role: string;
  preview: string;
  score: string;
  updatedAt: string;
};

export const activeSession: SessionModel = {
  scene: "Cafe counter order",
  role: "Friendly barista",
  opener: "Hi there! What can I get started for you today?",
  confidence: 0.92,
  labels: ["menu", "cashier", "iced drinks", "small talk"],
  mediaTitle: "counter-order.jpg",
  messages: [
    {
      id: "m1",
      role: "coach",
      text: "Hi there! What can I get started for you today?",
    },
    {
      id: "m2",
      role: "learner",
      text: "Can I have one iced latte and maybe a muffin?",
      feedback: {
        grammar: "The sentence works. Add 'please' to sound warmer in service situations.",
        moreNatural: "Could I get an iced latte and maybe a muffin, please?",
        usefulWords: ["could I get", "medium iced latte", "to go"],
      },
    },
    {
      id: "m3",
      role: "coach",
      text: "Of course. Do you want the latte for here or to go?",
    },
  ],
};

export const historyEntries: HistoryEntry[] = [
  {
    id: "h1",
    scene: "Restaurant lunch",
    role: "Server",
    preview: "You practiced ordering a sandwich combo and clarified drink options.",
    score: "Flow stable",
    updatedAt: "Today · 18:40",
  },
  {
    id: "h2",
    scene: "Office hallway",
    role: "Colleague",
    preview: "You made small talk about workload and asked a follow-up question.",
    score: "Tone improving",
    updatedAt: "Yesterday · 08:15",
  },
  {
    id: "h3",
    scene: "Street directions",
    role: "Passerby",
    preview: "You asked for the nearest subway and confirmed the walking route.",
    score: "Vocabulary boosted",
    updatedAt: "Mar 27 · 21:10",
  },
];
