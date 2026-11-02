type QuickReplyChipsProps = {
  replies: string[];
  disabled?: boolean;
  onPick: (reply: string) => void;
};

/** 快捷回复：一句话就能开口，避免「不知道说什么」卡住整轮练习。 */
export function QuickReplyChips({ replies, disabled = false, onPick }: QuickReplyChipsProps) {
  if (!replies.length) {
    return null;
  }

  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 pb-1 sm:px-6" aria-label="快捷回复">
      {replies.map((reply) => (
        <button
          key={reply}
          type="button"
          disabled={disabled}
          onClick={() => onPick(reply)}
          className="shrink-0 rounded-full border border-[#131311]/10 bg-white px-4 py-2 text-[12px] font-semibold text-stone-500 transition hover:border-[#131311] hover:text-[#131311] disabled:opacity-50"
        >
          {reply}
        </button>
      ))}
    </div>
  );
}
