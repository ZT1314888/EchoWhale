export type MessageRole = "coach" | "learner";

export type SampleScene = {
  id: string;
  title: string;
  body: string;
  imageSrc: string;
  imageAlt: string;
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

export type VoiceConversationItem = {
  role: "assistant" | "user";
  content: string;
};

export type VoiceBootstrapResult = {
  sessionId: string;
  deepgramAccessToken: string;
  deepgramWsUrl: string;
  expiresIn: number;
  agentSettings: Record<string, unknown>;
  session: SessionSummary;
};

export type VoiceCompleteInput = {
  conversation: VoiceConversationItem[];
  terminationReason: string;
  clientDiagnostics?: Record<string, unknown>;
};

export type VoiceCompleteResult = {
  session: SessionSummary;
  review: ReviewSummary;
};

export type AuthCredentials = {
  email: string;
  password: string;
};

export type RegisterPayload = AuthCredentials & {
  nickname: string;
};

export type EmailPayload = {
  email: string;
};

export type TokenPayload = {
  token: string;
};

export type ResetPasswordPayload = TokenPayload & {
  password: string;
};

export type AuthUser = {
  userId: string;
  email: string;
  nickname: string;
};

export type AuthSession = {
  accessToken: string;
  user: AuthUser;
};

export type AuthState = {
  status: "refreshing" | "anonymous" | "authenticated";
  user: AuthUser | null;
};

export type AppError = {
  code: string;
  message: string;
  reason?: string;
};
