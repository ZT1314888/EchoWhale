import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TextComposer } from "./TextComposer";

describe("TextComposer", () => {
  it("sends trimmed content with an abort signal and clears on success", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<TextComposer onSend={onSend} />);

    const input = screen.getByLabelText(/用文字继续练习/i);
    fireEvent.change(input, { target: { value: "  Could I get a latte?  " } });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));
    const [content, options] = onSend.mock.calls[0];
    expect(content).toBe("Could I get a latte?");
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(options.signal.aborted).toBe(false);
    // 清空发生在 await onSend 之后，是独立的一次 state 更新：断言要等它落地，
    // 否则在并行满载时会读到还没刷新的旧草稿。
    await waitFor(() => expect(input).toHaveValue(""));
    expect(screen.getByRole("button", { name: /发送/i })).toBeInTheDocument();
  });

  it("disables the input while sending and cancels through the abort signal", async () => {
    const onSend = vi.fn().mockImplementation(
      (_content: string, { signal }: { signal: AbortSignal }) =>
        new Promise<void>((_resolve, reject) => {
          signal.addEventListener("abort", () => {
            const abortError = new Error("aborted");
            abortError.name = "AbortError";
            reject(abortError);
          });
        }),
    );
    render(<TextComposer onSend={onSend} />);

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "One iced latte, please." },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    expect(screen.getByLabelText(/用文字继续练习/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /取消/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /取消/i }));

    await waitFor(() => {
      expect(onSend.mock.calls[0]?.[1].signal.aborted).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /发送/i })).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("One iced latte, please.");
  });

  it("keeps the draft when the send fails", async () => {
    const onSend = vi.fn().mockRejectedValue({
      code: "TURN_SUBMIT_FAILED",
      message: "boom",
    });
    render(<TextComposer onSend={onSend} />);

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "Keep me, please." },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /发送/i })).toBeEnabled();
    });
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("Keep me, please.");
  });

  it("does not send empty or whitespace-only content", () => {
    const onSend = vi.fn();
    render(<TextComposer onSend={onSend} />);

    const input = screen.getByLabelText(/用文字继续练习/i);
    expect(screen.getByRole("button", { name: /发送/i })).toBeDisabled();

    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: /发送/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /发送/i }));
    expect(onSend).not.toHaveBeenCalled();

    // Enter 走的是 handleSend 而不是按钮的 disabled 短路，空草稿也必须被拦住。
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends on Enter but leaves Shift+Enter for a newline", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<TextComposer onSend={onSend} />);

    const input = screen.getByLabelText(/用文字继续练习/i);
    fireEvent.change(input, { target: { value: "One flat white, please." } });

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));
    expect(onSend.mock.calls[0][0]).toBe("One flat white, please.");
  });

  it("drives the draft through the controlled props without losing the value", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    const onDraftChange = vi.fn();
    const { rerender } = render(<TextComposer onSend={onSend} draft="从金句锦囊插入的句子 " onDraftChange={onDraftChange} />);

    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("从金句锦囊插入的句子 ");

    fireEvent.change(screen.getByLabelText(/用文字继续练习/i), {
      target: { value: "从金句锦囊插入的句子 To be honest…" },
    });
    expect(onDraftChange).toHaveBeenCalledWith("从金句锦囊插入的句子 To be honest…");

    rerender(<TextComposer onSend={onSend} draft="从金句锦囊插入的句子 To be honest…" onDraftChange={onDraftChange} />);
    expect(screen.getByLabelText(/用文字继续练习/i)).toHaveValue("从金句锦囊插入的句子 To be honest…");

    fireEvent.click(screen.getByRole("button", { name: /发送/i }));

    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));
    // 受控模式下清空同样走 onDraftChange，组件自身不藏第二份草稿。
    expect(onDraftChange).toHaveBeenLastCalledWith("");
  });
});
