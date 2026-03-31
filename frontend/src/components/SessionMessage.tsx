import type { MessageModel } from "../data/mockSession";

const roleCopy: Record<MessageModel["role"], string> = {
  coach: "Coach",
  learner: "You",
};

const roleStyles: Record<MessageModel["role"], string> = {
  coach: "border-white/10 bg-white/5 text-[var(--color-foam)]",
  learner: "border-[var(--color-aqua)]/25 bg-[var(--color-aqua)]/10 text-[var(--color-mist)]",
};

export function SessionMessage({ message }: { message: MessageModel }) {
  return (
    <article className={`rounded-[26px] border p-4 ${roleStyles[message.role]}`}>
      <div className="flex items-center justify-between gap-4">
        <span className="eyebrow">{roleCopy[message.role]}</span>
        <span className="text-xs uppercase tracking-[0.32em] text-white/35">{message.id}</span>
      </div>
      <p className="mt-3 text-sm leading-7">{message.text}</p>
    </article>
  );
}
