import type { SessionModel } from "../data/mockSession";

import { FeedbackCard } from "./FeedbackCard";
import { SessionMessage } from "./SessionMessage";

export function SessionStage({ session }: { session: SessionModel }) {
  const learnerMessage = session.messages.find((message) => message.role === "learner");

  return (
    <section className="panel-shell space-y-6" aria-label="Practice cockpit">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">Session engine</p>
          <h2 className="font-display text-3xl text-[var(--color-foam)]">Practice cockpit</h2>
        </div>
        <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.24em] text-white/45">
          Scene -> coach -> feedback
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.85fr)]">
        <div className="space-y-4 rounded-[32px] border border-white/10 bg-black/10 p-5">
          <div className="rounded-[26px] border border-[var(--color-sun)]/20 bg-[var(--color-sun)]/10 p-4 text-sm leading-7 text-[var(--color-foam)]">
            <span className="eyebrow">Opener</span>
            <p className="mt-3">{session.opener}</p>
          </div>

          <div className="space-y-3">
            {session.messages.map((message) => (
              <SessionMessage key={message.id} message={message} />
            ))}
          </div>
        </div>

        {learnerMessage?.feedback ? <FeedbackCard feedback={learnerMessage.feedback} /> : null}
      </div>
    </section>
  );
}
