import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, TrendingUp } from "lucide-react";

import { MedalGrid } from "../components/MedalGrid";
import { PageShell, RadarChart, ScoreRing } from "../components/ui";
import { getLearnerProfile } from "../services/learnerApi";
import type { LearnerProfileOverview } from "../types/app";
import { CEFR_LEVELS, buildMedals, cefrLevelIndex, toCefrDisplay } from "../utils/progressStats";

export function ProgressPage() {
  const [profile, setProfile] = useState<LearnerProfileOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    getLearnerProfile()
      .then((value) => {
        if (alive) {
          setProfile(value);
        }
      })
      .catch((reason: { message?: string }) => {
        if (alive) {
          setError(reason.message ?? "学习进度加载失败。");
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  // 空档案定案：practicedTurnCount === 0 即空态（有轮数必有场景，判据充分）。
  const hasData = profile !== null && profile.practicedTurnCount > 0;
  const showOverview = !loading && !error && hasData && profile !== null;

  return (
    <PageShell wide>
      <div className="flex flex-wrap items-end justify-between gap-4">
        {/* h1 的可访问名必须是中文原文（路由测试按 level 1 精确匹配），
            可见的英文标题行整体 aria-hidden。 */}
        <div className="max-w-2xl">
          <h1 className="font-display text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]">
            <span className="sr-only">我的进度</span>
            <span aria-hidden="true">
              Your season so far
              <span className="font-serif-accent ml-2 align-middle text-[0.62em] font-medium text-stone-400">
                我的进度
              </span>
            </span>
          </h1>
          <p className="mt-2 text-[13.5px] leading-relaxed text-stone-500">
            由真实练习数据生成的长期画像：水平估计、常见错误与练过的场景。
          </p>
        </div>
      </div>

      {error ? (
        <p className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] font-semibold text-rose-700">
          {error}
        </p>
      ) : null}
      {loading ? <p className="mt-6 text-[13px] text-stone-400">正在加载学习进度…</p> : null}

      {!loading && !error && !hasData ? (
        <section className="mt-6 rounded-[28px] border border-dashed border-[#131311]/15 bg-white/60 p-12 text-center">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">
            <TrendingUp size={24} aria-hidden="true" />
          </span>
          <h2 className="font-display mt-5 text-xl font-bold">还没有练习数据</h2>
          <p className="mx-auto mt-1.5 max-w-sm text-[13.5px] leading-relaxed text-stone-500">
            上传一张生活场景图片开始第一次练习，完成后这里会展示你的水平估计、常见错误和练习过的场景。
          </p>
          <Link
            to="/"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#131311] px-6 py-3.5 text-[13.5px] font-bold text-white"
          >
            上传图片开始第一次练习
            <ArrowUpRight size={15} className="text-[#d8f34e]" aria-hidden="true" />
          </Link>
        </section>
      ) : null}

      {showOverview && profile ? (
        <>
          <div className="noise relative mt-6 overflow-hidden rounded-[32px] bg-[#131311] text-white">
            <div className="grid-pattern-light pointer-events-none absolute inset-0" />
            <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[#4f46e5]/35 blur-[110px]" />
            <div className="relative grid gap-8 p-8 sm:p-10 lg:grid-cols-[1.1fr_1fr_1fr]">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-white/40">Level · 水平估计</p>
                <p className="font-display mt-3 text-[24px] font-bold leading-tight">
                  {profile.cefrEstimate ? (
                    toCefrDisplay(profile.cefrEstimate)
                  ) : (
                    <span className="text-white/60">暂无水平估计，继续练习后会自动生成</span>
                  )}
                </p>
                <p className="mt-2 text-[12px] leading-relaxed text-white/45">
                  根据你的练习表现自动生成，仅供学习参考。
                </p>

                {/* 未估计时不点亮任何一段 —— 六段全灰，而不是默认停在 A1。 */}
                <div className="mt-5">
                  <div className="flex justify-between text-[11px] font-bold uppercase tracking-widest text-white/40">
                    <span>CEFR journey</span>
                    <span>{cefrLevelIndex(profile.cefrEstimate) + 1} / {CEFR_LEVELS.length}</span>
                  </div>
                  <div className="mt-2 flex gap-1.5">
                    {CEFR_LEVELS.map((level, index) => (
                      <span
                        key={level}
                        title={level}
                        className={`h-2 flex-1 rounded-full ${
                          index <= cefrLevelIndex(profile.cefrEstimate) ? "bg-[#d8f34e]" : "bg-white/12"
                        }`}
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-5 rounded-[24px] border border-white/10 bg-white/[0.05] p-5">
                <ScoreRing score={0} size={124} stroke={11} label="—" dark />
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#d8f34e]">Score · 综合得分</p>
                  <p className="font-display mt-1.5 text-[19px] font-bold leading-tight">—</p>
                  <p className="mt-1 text-[12px] leading-relaxed text-white/50">
                    后端不提供维度评分，这一格保持空态。
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 content-center gap-2.5">
                {[
                  ["Sessions", "场次", "—"],
                  ["Turns", "轮数", String(profile.practicedTurnCount)],
                  ["Airtime", "时长", "—"],
                  ["Words", "词数", "—"],
                ].map(([en, cn, value]) => (
                  <div key={en} className="rounded-[20px] border border-white/10 bg-white/[0.05] p-4">
                    <p className="font-display text-[22px] font-bold">{value}</p>
                    <p className="text-[11px] font-semibold text-white/45">
                      {en} {cn}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1fr]">
            <section className="rounded-[28px] border border-[#131311]/8 bg-[#faf9f6] p-6">
              <h2 className="text-[13px] font-bold">
                Skill balance <span className="font-normal text-stone-400">能力均衡</span>
              </h2>
              <div className="mt-2">
                <RadarChart
                  scores={[
                    { label: "Fluency", value: 0 },
                    { label: "Vocab", value: 0 },
                    { label: "Grammar", value: 0 },
                    { label: "Pronun", value: 0 },
                    { label: "Coher", value: 0 },
                  ]}
                />
              </div>
              <p className="mt-2 rounded-2xl bg-[#131311] p-3 text-center text-[12px] font-semibold text-white/70">
                五维雷达需要评分数据，后端暂未提供。
              </p>
            </section>

            <section className="rounded-[28px] border border-[#131311]/8 bg-white p-6">
              <h2 className="text-[13px] font-bold">
                累计轮数 <span className="font-normal text-stone-400">Turns</span>
              </h2>
              <p className="font-display mt-3 text-[32px] font-bold tracking-tight">{profile.practicedTurnCount} 轮</p>
              {profile.updatedAt ? (
                <p className="mt-1 text-[12.5px] text-stone-400">最近更新：{profile.updatedAt}</p>
              ) : null}

              <div className="mt-5 space-y-4">
                <div>
                  <h3 className="text-[12.5px] font-bold text-[#131311]">常见错误类型</h3>
                  {profile.errorTypes.length ? (
                    <ul className="mt-2 space-y-1.5">
                      {profile.errorTypes.map((errorType) => (
                        <li key={errorType.category} className="flex items-center justify-between text-[13px]">
                          <span className="text-stone-600">{errorType.label}</span>
                          <span className="font-bold text-[#131311]">{errorType.count} 次</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1.5 text-[13px] text-stone-400">暂无错误记录，继续保持。</p>
                  )}
                </div>

                <div>
                  <h3 className="text-[12.5px] font-bold text-[#131311]">练习场景</h3>
                  {profile.scenes.length ? (
                    <ul className="mt-2 space-y-1.5">
                      {profile.scenes.map((scene) => (
                        <li key={scene.sceneTitle} className="flex items-center justify-between text-[13px]">
                          <span className="text-stone-600">{scene.sceneTitle}</span>
                          <span className="font-bold text-[#131311]">{scene.count} 次</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1.5 text-[13px] text-stone-400">暂无场景记录，继续保持。</p>
                  )}
                </div>
              </div>
            </section>
          </div>

          <div className="mt-5">
            <MedalGrid medals={buildMedals(profile.practicedTurnCount)} />
          </div>
        </>
      ) : null}
    </PageShell>
  );
}
