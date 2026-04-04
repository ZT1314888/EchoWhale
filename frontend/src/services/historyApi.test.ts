import { afterEach, describe, expect, it, vi } from "vitest";

import * as historyApi from "./historyApi";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("historyApi", () => {
  it("maps backend history list items into frontend history entries", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 200,
        message: "Success",
        data: [
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
      }),
    }) as typeof fetch;

    const entries = await historyApi.listHistorySessions();

    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({
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
  });

  it("maps backend history detail into frontend detail data", async () => {
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
            labels: ["coffee", "menu"],
            messages: [
              {
                message_id: "msg_1",
                role: "assistant",
                text: "Hi there, what can I get started for you today?",
              },
            ],
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
    expect(detail.review.feedback.moreNatural.body).toBe("Could I get an iced latte, please?");
  });
});
