import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandHeader } from "../components/BrandHeader";
import { resetPassword } from "../services/authApi";

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const params = new URLSearchParams(location.search);
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
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
    if (!token) {
      setError("重置链接缺少 token。");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      await resetPassword({ token, password });
      setSuccess(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "密码重置失败，请稍后重试。");
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
            <h2>设置一个新的登录密码</h2>
            <p className="muted-text">重置密码后，旧 refresh 会话会被撤销。这样做的目的，是避免旧设备继续保留可用登录态。</p>
          </section>

          <section className="panel-card auth-panel auth-panel--rounded">
            <div className="section-header section-header--stack">
              <p className="eyebrow">Reset Password</p>
              <h1>重置密码</h1>
              <p className="muted-text">请输入一个包含字母和数字的新密码。</p>
            </div>

            <form className="auth-form" onSubmit={onSubmit}>
              <label className="field-label" htmlFor="reset-password">
                新密码
              </label>
              <input
                id="reset-password"
                className="input-field"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {error ? <p className="form-error">{error}</p> : null}
              {success ? <p className="muted-text">密码已更新，现在可以返回登录。</p> : null}
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "提交中…" : "确认重置密码"}
              </button>
            </form>

            <button className="link-button" type="button" onClick={() => navigate("/login")}>
              返回登录
            </button>
          </section>
        </main>
      </div>
    </div>
  );
}
