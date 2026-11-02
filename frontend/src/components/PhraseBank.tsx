import { Lightbulb, Plus, X } from "lucide-react";

type PhraseBankProps = {
  phrases: string[];
  onInsert: (phrase: string) => void;
  onDismiss: () => void;
};

/** 金句锦囊：点一条追加到输入框。全部短语来自场景标签，不是编造的句式库。 */
export function PhraseBank({ phrases, onInsert, onDismiss }: PhraseBankProps) {
  if (!phrases.length) {
    return null;
  }

  return (
    <section className="rounded-[28px] border border-[#131311]/8 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-1.5 text-[13px] font-bold">
          <Lightbulb size={15} className="text-amber-500" aria-hidden="true" />
          金句锦囊
        </h2>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="收起金句锦囊"
          className="grid h-7 w-7 place-items-center rounded-full bg-stone-100 text-stone-400 transition hover:text-[#131311]"
        >
          <X size={13} aria-hidden="true" />
        </button>
      </div>
      <div className="mt-3 space-y-2">
        {phrases.map((phrase, index) => (
          <button
            key={phrase}
            type="button"
            onClick={() => onInsert(phrase)}
            className="group flex w-full items-center gap-2 rounded-xl bg-stone-50 p-3 text-left text-[12.5px] font-semibold transition hover:bg-[#131311] hover:text-white"
          >
            <span className="font-mono text-[11px] text-stone-300 group-hover:text-[#d8f34e]">
              {String(index + 1).padStart(2, "0")}
            </span>
            {phrase}
            <Plus size={14} className="ml-auto opacity-40" aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
