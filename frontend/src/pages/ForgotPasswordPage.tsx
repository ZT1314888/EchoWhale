import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthLayout } from "../components/AuthLayout";
import { AuthSubmitButton } from "../components/AuthSubmitButton";
import { AuthTextField } from "../components/AuthTextField";
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
      <main className="auth-loading-stage">
        <div className="auth-loading-spinner" />
        <p className="auth-loading-text">正在恢复登录状态…</p>
      </main>
    );
  }

  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim();

    if (!normalizedEmail) {
      setError("请输入邮箱地址");
      return;
    }

    setError("");
    setSubmitted(false);
    setSubmitting(true);

    try {
      await forgotPassword({ email: normalizedEmail });
      setSubmitted(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "密码找回请求失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      brand={
        <AuthBrandPanel
          title={
            <>
              找回你的
              <br />
              登录入口
            </>
          }
          description="输入注册邮箱，我们会发送密码重置链接。无论邮箱是否注册，页面都会给出相同的提示，以避免泄露账号是否存在。"
        >
          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              </div>
              <span className="auth-feature-item__text">重置链接有效期有限，请尽快使用</span>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <span className="auth-feature-item__text">重置成功后旧登录会话将被撤销</span>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
              </div>
              <span className="auth-feature-item__text">没收到邮件？请检查垃圾邮件文件夹</span>
            </div>
          </div>
        </AuthBrandPanel>
      }
    >
      <AuthFormCard title="忘记密码" subtitle="输入注册邮箱，接收密码重置链接">
        <form className="auth-form-modern" onSubmit={onSubmit}>
          <AuthTextField
            id="forgot-password-email"
            label="邮箱地址"
            type="email"
            placeholder="your@email.com"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          {error ? <AuthAlert message={error} /> : null}
          {submitted ? (
            <AuthAlert variant="info" message="如果该邮箱已注册，重置邮件已发送，请检查收件箱（含垃圾邮件）。" />
          ) : null}
          <AuthSubmitButton submitting={submitting} submittingText="发送中…">
            发送重置邮件
          </AuthSubmitButton>
        </form>

        <div className="auth-form-divider">
          <span className="auth-form-divider__text">想起密码了？</span>
        </div>
        <button
          type="button"
          className="auth-form-secondary"
          onClick={() => navigate("/login", { state: { prefillEmail: email } })}
        >
          返回登录
        </button>
      </AuthFormCard>
    </AuthLayout>
  );
}
