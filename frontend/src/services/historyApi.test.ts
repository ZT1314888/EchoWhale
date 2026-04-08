import { afterEach, describe, expect, it, vi } from "vitest";

import * as historyApi from "./historyApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("historyApi", () => {
  it("maps backend history list payload into a paged result", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          items: [
            {
              id: "sess_123",
              practiced_at: "2026-04-04 15:20",
              status: "已完成 1 轮",
              scene_title: "咖啡店柜台点单",
              role_label: "店员对话",
              preview: "你已经说清楚主要需求。",
              tags: ["coffee", "menu"],
              review_title: "本轮回响",
              review_summary: "下一轮再补一条细节。",
            },
          ],
          page: {
            has_more: true,
            next_cursor: "cursor_123",
          },
        },
      }),
    }) as typeof fetch;

    const result = await historyApi.listHistorySessions({ limit: 20 });

    expect(result.items).toHaveLength(1);
    expect(result.items[0]).toEqual({
      id: "sess_123",
      practicedAt: "2026-04-04 15:20",
      status: "已完成 1 轮",
      sceneTitle: "咖啡店柜台点单",
      roleLabel: "店员对话",
      preview: "你已经说清楚主要需求。",
      tags: ["coffee", "menu"],
      reviewTitle: "本轮回响",
      reviewSummary: "下一轮再补一条细节。",
    });
    expect(result.page.hasMore).toBe(true);
    expect(result.page.nextCursor).toBe("cursor_123");
  });

  it("maps backend history detail into overview data without replay messages", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          entry: {
            id: "sess_123",
            practiced_at: "2026-04-04 15:20",
            status: "已完成 1 轮",
            scene_title: "咖啡店柜台点单",
            role_label: "店员对话",
            preview: "你已经说清楚主要需求。",
            tags: ["coffee", "menu"],
            review_title: "本轮回响",
            review_summary: "下一轮再补一条细节。",
          },
          session: {
            session_id: "sess_123",
            media_id: "med_123",
            scene: "coffee_shop",
            role: "barista",
            opener: "Hi there, what can I get started for you today?",
            status: "active",
            visual_anchors: ["counter", "menu board"],
            vocab_candidates: ["coffee", "menu"],
            total_messages: 12,
          },
          review: {
            session_id: "sess_123",
            title: "本轮回响",
            highlight: "你已经说清楚主要需求。",
            next_try: "下一轮再补一条细节。",
            feedback: {
              grammar: { title: "Grammar", body: "Your meaning is clear." },
              more_natural: {
                title: "More Natural",
                body: "Could I get an iced latte, please?",
              },
              useful_words: {
                title: "Useful Words",
                words: ["latte", "size", "iced"],
                body: "把这些词带进下一轮回答，会更自然。",
              },
              next_step: {
                title: "Next Step",
                body: "下一轮试着在一句主回应后再补一句细节。",
              },
            },
          },
        },
      }),
    }) as typeof fetch;

    const detail = await historyApi.getHistorySession("sess_123");

    expect(detail.entry.reviewTitle).toBe("本轮回响");
    expect(detail.session.id).toBe("sess_123");
    expect(detail.session.totalMessages).toBe(12);
    expect(detail.review.feedback.moreNatural.body).toBe("Could I get an iced latte, please?");
  });

  it("maps backend replay messages into paged playback data", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: {
          items: [
            {
              message_id: "msg_2",
              role: "user",
              text: "Could I get an iced latte, please?",
            },
            {
              message_id: "msg_3",
              role: "assistant",
              text: "Of course. What size would you like?",
            },
          ],
          page: {
            has_more: true,
            next_cursor: "msg_2",
          },
        },
      }),
    }) as typeof fetch;

    const replay = await historyApi.getHistorySessionMessages("sess_123", { limit: 20 });

    expect(replay.items).toEqual([
      {
        id: "msg_2",
        role: "learner",
        label: "你 · 本轮回答",
        content: "Could I get an iced latte, please?",
      },
      {
        id: "msg_3",
        role: "coach",
        label: "教练 · 追问",
        content: "Of course. What size would you like?",
      },
    ]);
    expect(replay.page.hasMore).toBe(true);
    expect(replay.page.nextCursor).toBe("msg_2");
  });
});
