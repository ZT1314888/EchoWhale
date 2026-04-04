export type MessageRole = "coach" | "learner";

export type SampleScene = {
  id: string;
  title: string;
  body: string;
  imageClass: string;
  roleLabel: string;
  openingPrompt: string;
  tags: string[];
  liveHint: string;
};

export type UploadDraft = {
  source: "sample" | "file";
  sampleSceneId?: string;
  fileName?: string;
  file?: File;
  uploadedMedia?: UploadedMedia;
};

export type UploadedMedia = {
  mediaId: string;
  filename: string;
  contentType: string;
  fileSize: number;
  storageKey: string;
  previewUrl: string;
  previewUrlExpiresAt: string;
  uploadStatus: string;
};

export type PracticeMessage = {
  id: string;
  role: MessageRole;
  label: string;
  content: string;
};

export type FeedbackMetric = {
  title: string;
  body: string;
};

export type UsefulWordsMetric = {
  title: string;
  words: string[];
  body: string;
};

export type PracticeFeedback = {
  grammar: FeedbackMetric;
  moreNatural: FeedbackMetric;
  usefulWords: UsefulWordsMetric;
  nextStep: FeedbackMetric;
};

export type SessionSummary = {
  id: string;
  title: string;
  roleLabel: string;
  openingPrompt: string;
  tags: string[];
  liveHint: string;
  voiceTitle: string;
  voiceBody: string;
  messages: PracticeMessage[];
};

export type ReviewSummary = {
  sessionId: string;
  title: string;
  highlight: string;
  nextTry: string;
  feedback: PracticeFeedback;
};

export type HistoryEntry = {
  id: string;
  practicedAt: string;
  status: string;
  sceneTitle: string;
  roleLabel: string;
  preview: string;
  tags: string[];
  reviewTitle: string;
  reviewSummary: string;
};

export type HistoryDetail = {
  entry: HistoryEntry;
  session: SessionSummary;
  review: ReviewSummary;
};

export type PracticeTurnInput = {
  content: string;
};

export type SubmitPracticeTurnResult = {
  messages: PracticeMessage[];
  feedback: PracticeFeedback;
};

export type AuthCredentials = {
  email: string;
  password: string;
};

export type RegisterPayload = AuthCredentials & {
  nickname: string;
};

export type AuthResult = {
  userName: string;
};

export type AppError = {
  code: string;
  message: string;
};
