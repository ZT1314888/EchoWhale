import { Award, Check, Lock } from "lucide-react";

import { countEarnedMedals, type Medal } from "../utils/progressStats";

type MedalGridProps = {
  medals: Medal[];
};

/** 成就墙。锁定态如实写出解锁所需的后端字段，不用编造进度填充。 */
export function MedalGrid({ medals }: MedalGridProps) {
  const earnedCount = countEarnedMedals(medals);

  return (
    <section className="rounded-[28px] border border-[#131311]/8 bg-white p-6 sm:p-7">
      <h2 className="flex items-center gap-2 text-[13px] font-bold">
        <Award size={16} aria-hidden="true" />
        成就
        <span className="font-normal text-stone-400">
          {earnedCount} / {medals.length} 已解锁
        </span>
      </h2>

      <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        {medals.map((medal) => (
          <div
            key={medal.id}
            className={`rounded-3xl border p-4 text-center transition ${
              medal.earned
                ? "border-[#131311] bg-[#131311] text-white"
                : "border-[#131311]/8 bg-stone-50 opacity-55 grayscale"
            }`}
          >
            <span
              className={`mx-auto grid h-11 w-11 place-items-center rounded-2xl ${
                medal.earned ? "bg-[#d8f34e] text-[#131311]" : "bg-stone-200 text-stone-400"
              }`}
            >
              {medal.earned ? <Award size={19} aria-hidden="true" /> : <Lock size={17} aria-hidden="true" />}
            </span>
            <p className="mt-2.5 text-[12.5px] font-bold leading-tight">{medal.title}</p>
            <p className={`text-[11px] ${medal.earned ? "text-white/50" : "text-stone-400"}`}>{medal.desc}</p>
            <p
              className={`mx-auto mt-2 flex w-fit items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold ${
                medal.earned ? "bg-[#d8f34e] text-[#131311]" : "bg-stone-200 text-stone-500"
              }`}
            >
              {medal.earned ? (
                <>
                  <Check size={10} strokeWidth={3.5} aria-hidden="true" />
                  已解锁
                </>
              ) : (
                medal.requirement
              )}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
