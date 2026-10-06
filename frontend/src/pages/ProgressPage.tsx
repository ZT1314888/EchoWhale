import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
import { getLearnerProfile } from "../services/learnerApi";
import type { LearnerProfileOverview } from "../types/app";

// CEFR 等级是服务端下发的封闭集合值（A1..C2），中文文案映射归前端展示。
const CEFR_LEVEL_LABELS: Record<string, string> = {
  A1: "入门",
  A2: "基础",
  B1: "进阶",
  B2: "中高",
  C1: "高级",
  C2: "精通",
};

function toCefrDisplay(cefrEstimate: string): string {
  return `${CEFR_LEVEL_LABELS[cefrEstimate] ?? cefrEstimate}（${cefrEstimate}）`;
}

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
    <div className="page-shell">
      <div className="page-frame">
        <BrandHeader />

        <main className="page-grid page-grid--progress">
          <section className="panel-section">
            <div className="section-header">
              <div>
                <p className="eyebrow eyebrow--brand">Learner Progress</p>
                <h1>我的进度</h1>
              </div>
            </div>

            {error ? <p className="form-error">{error}</p> : null}
            {loading ? <p className="muted-text">正在加载学习进度…</p> : null}

            {!loading && !error && !hasData ? (
              <section className="panel-card panel-card--soft empty-state">
                <h2>还没有练习数据</h2>
                <p className="muted-text">
                  上传一张生活场景图片开始第一次练习，完成后这里会展示你的水平估计、常见错误和练习过的场景。
                </p>
                <Link className="ghost-button" to="/">
                  上传图片开始第一次练习
                </Link>
              </section>
            ) : null}

            {showOverview && profile ? (
              <>
                <section className="panel-card progress-card">
                  <h2>水平估计</h2>
                  {profile.cefrEstimate ? (
                    <p className="progress-metric-value">{toCefrDisplay(profile.cefrEstimate)}</p>
                  ) : (
                    <p className="muted-text">暂无水平估计，继续练习后会自动生成</p>
                  )}
                  <p className="progress-meta">根据你的练习表现自动生成，仅供学习参考。</p>
                </section>

                <section className="panel-card progress-card">
                  <h2>常见错误类型</h2>
                  {profile.errorTypes.length ? (
                    <ul className="progress-list">
                      {profile.errorTypes.map((errorType) => (
                        <li key={errorType.category}>
                          <span>{errorType.label}</span>
                          <span className="progress-meta">{errorType.count} 次</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted-text">暂无错误记录，继续保持。</p>
                  )}
                </section>

                <section className="panel-card progress-card">
                  <h2>练习场景</h2>
                  {profile.scenes.length ? (
                    <ul className="progress-list">
                      {profile.scenes.map((scene) => (
                        <li key={scene.sceneTitle}>
                          <span>{scene.sceneTitle}</span>
                          <span className="progress-meta">{scene.count} 次</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted-text">暂无场景记录，继续保持。</p>
                  )}
                </section>

                <section className="panel-card progress-card">
                  <h2>累计轮数</h2>
                  <p className="progress-metric-value">{profile.practicedTurnCount} 轮</p>
                  {profile.updatedAt ? (
                    <p className="progress-meta">最近更新：{profile.updatedAt}</p>
                  ) : null}
                </section>
              </>
            ) : null}
          </section>
        </main>
      </div>
    </div>
  );
}
