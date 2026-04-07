import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandHeader } from "../components/BrandHeader";
import { forgotPassword } from "../services/authApi";

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const routeState = location.state as { prefillEmail?: string } | null;
  const [email, setEmail] = useState(routeState?.prefillEmail ?? "");
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (auth.status === "refreshing") {
    return (
      <main className="empty-stage">
        <h1>正在恢复登录状态…</h1>
      </main>
    );
  }

  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await forgotPassword({ email });
      setSubmitted(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "密码找回请求失败，请稍后重试。");
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
            <h2>恢复你的登录入口</h2>
            <p className="muted-text">如果这封邮箱存在，我们会发送一封密码重置邮件。这样做的目的，是避免页面直接暴露账号是否存在。</p>
          </section>

          <section className="panel-card auth-panel auth-panel--rounded">
            <div className="section-header section-header--stack">
              <p className="eyebrow">Forgot Password</p>
              <h1>找回密码</h1>
              <p className="muted-text">输入注册邮箱，我们会发送密码重置链接。</p>
            </div>

            <form className="auth-form" onSubmit={onSubmit}>
              <label className="field-label" htmlFor="forgot-password-email">
                邮箱
              </label>
              <input
                id="forgot-password-email"
                className="input-field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              {error ? <p className="form-error">{error}</p> : null}
              {submitted ? <p className="muted-text">如果邮箱有效，重置邮件已经发送，请检查收件箱。</p> : null}
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "发送中…" : "发送重置邮件"}
              </button>
            </form>

            <button className="link-button" type="button" onClick={() => navigate("/login", { state: { prefillEmail: email } })}>
              返回登录
            </button>
          </section>
        </main>
      </div>
    </div>
  );
}
