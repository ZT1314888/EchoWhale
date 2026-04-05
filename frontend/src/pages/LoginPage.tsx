import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandHeader } from "../components/BrandHeader";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const routeState = location.state as { prefillEmail?: string } | null;
  const [email, setEmail] = useState(routeState?.prefillEmail ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loginSucceeded, setLoginSucceeded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const nextPath = new URLSearchParams(location.search).get("next") || "/";

  if (auth.status === "refreshing") {
    return (
      <main className="empty-stage">
        <h1>正在恢复登录状态…</h1>
      </main>
    );
  }

  if (auth.status === "authenticated") {
    return <Navigate to={nextPath} replace state={loginSucceeded ? { loginSuccess: true } : undefined} />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await auth.login({ email, password });
      setLoginSucceeded(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "登录失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell page-shell--auth">
      <div className="page-frame">
        <BrandHeader />

        <main className="auth-layout">
          <section className="panel-card auth-aside">
            <p className="eyebrow eyebrow--brand">EchoWhale</p>
            <h2>回到你的安静开口通道</h2>
            <p className="muted-text">
              轻量登录后，继续以场景为起点的口语练习；每轮结束后，只保留一份简短回响。
            </p>
            <div className="pill-row">
              <span className="info-pill">场景上传</span>
              <span className="info-pill">语音优先</span>
            </div>
          </section>

          <section className="panel-card auth-panel">
            <div className="section-header section-header--stack">
              <p className="eyebrow">Welcome Back</p>
              <h1>欢迎回来</h1>
              <p className="muted-text">轻量登录后，继续你刚才停下来的那一轮场景口语练习。</p>
            </div>

            <button className="social-button" type="button">
              使用 Google 继续（暂未开放）
            </button>
            <button className="social-button social-button--dark" type="button">
              使用 GitHub 继续（暂未开放）
            </button>

            <form className="auth-form" onSubmit={onSubmit}>
              <label className="field-label" htmlFor="login-email">
                邮箱
              </label>
              <input
                id="login-email"
                className="input-field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <label className="field-label" htmlFor="login-password">
                密码
              </label>
              <input
                id="login-password"
                className="input-field"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {error ? <p className="form-error">{error}</p> : null}
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "登录中…" : "继续进入练习"}
              </button>
            </form>

            <p className="muted-text">第一次来到这里？一步创建账号，把每次练习的回响都保存下来。</p>
            <button className="link-button" type="button" onClick={() => navigate("/register")}>
              去注册
            </button>
          </section>
        </main>
      </div>
    </div>
  );
}
