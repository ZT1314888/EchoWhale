import { useRef, useState, type KeyboardEvent } from "react";

type TextComposerProps = {
  disabled?: boolean;
  onSend: (content: string, options: { signal: AbortSignal }) => Promise<void>;
};

export function TextComposer({ disabled = false, onSend }: TextComposerProps) {
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const canSend = !disabled && !sending && content.trim().length > 0;

  async function handleSend() {
    if (!canSend) {
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setSending(true);
    try {
      await onSend(content.trim(), { signal: controller.signal });
      setContent("");
    } catch {
      // 失败与取消时保留已输入内容便于重发；错误提示由页面负责展示。
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className="text-composer" data-testid="text-composer">
      <textarea
        className="text-composer__input"
        aria-label="用文字继续练习"
        placeholder="也可以用文字继续这轮对话…"
        rows={2}
        value={content}
        disabled={disabled || sending}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {sending ? (
        <button
          className="text-composer__send text-composer__send--cancel"
          type="button"
          onClick={handleCancel}
        >
          取消
        </button>
      ) : (
        <button
          className="primary-button text-composer__send"
          type="button"
          onClick={() => void handleSend()}
          disabled={!canSend}
        >
          发送
        </button>
      )}
    </div>
  );
}
