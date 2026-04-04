import { describe, expect, it } from "vitest";

import { login, submitPracticeTurn } from "./mockApi";

describe("mockApi", () => {
  it("submits a learner turn and returns an appended coach reply with review data", async () => {
    const result = await submitPracticeTurn("session-coffee", {
      content: "Could I also get it to go?",
    });

    expect(result.messages.at(-2)?.role).toBe("learner");
    expect(result.messages.at(-2)?.content).toBe("Could I also get it to go?");
    expect(result.messages.at(-1)?.role).toBe("coach");
    expect(result.feedback.grammar.title).toBe("Grammar");
    expect(result.feedback.usefulWords.words).toContain("to go");
  });

  it("rejects login when the email is blank", async () => {
    await expect(login({ email: "", password: "secret123" })).rejects.toMatchObject({
      code: "AUTH_INVALID",
      message: "请输入邮箱地址。",
    });
  });
});
