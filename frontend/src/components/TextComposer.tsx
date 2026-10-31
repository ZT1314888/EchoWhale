import { useRef, useState, type KeyboardEvent } from "react";

type TextComposerProps = {
  disabled?: boolean;
  onSend: (content: string, options: { signal: AbortSignal }) => Promise<void>;
  /** 受控草稿。金句锦囊要往输入框里追加内容，省略时组件自己持有草稿。 */
  draft?: string;
  onDraftChange?: (draft: string) => void;
};

export function TextComposer({ disabled = false, onSend, draft, onDraftChange }: TextComposerProps) {
  const [innerContent, setInnerContent] = useState("");
  const content = draft ?? innerContent;
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const canSend = !disabled && !sending && content.trim().length > 0;

  function updateContent(next: string) {
    if (onDraftChange) {
      onDraftChange(next);
    } else {
      setInnerContent(next);
    }
  }

  async function handleSend() {
    if (!canSend) {
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setSending(true);
    try {
      await onSend(content.trim(), { signal: controller.signal });
      updateContent("");
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
    <div
      className="glass flex items-end gap-2.5 rounded-2xl border border-[#131311]/10 bg-white/80 p-3"
      data-testid="text-composer"
    >
      <textarea
        className="w-full resize-none rounded-2xl border border-[#131311]/12 bg-stone-50 p-3.5 text-[14px] outline-none transition placeholder:text-stone-400 focus:border-[#131311] focus:bg-white disabled:opacity-60"
        aria-label="用文字继续练习"
        placeholder="也可以用文字继续这轮对话…"
        rows={2}
        value={content}
        disabled={disabled || sending}
        onChange={(event) => updateContent(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {sending ? (
        <button
          className="grid h-[52px] shrink-0 place-items-center rounded-2xl border border-[#131311]/12 bg-white px-4 text-[13px] font-bold text-stone-600 transition hover:border-[#131311]"
          type="button"
          onClick={handleCancel}
        >
          取消
        </button>
      ) : (
        <button
          className="grid h-[52px] shrink-0 place-items-center rounded-2xl bg-[#131311] px-5 text-[13px] font-bold text-[#d8f34e] transition hover:bg-black disabled:opacity-30"
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
