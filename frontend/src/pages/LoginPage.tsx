import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthLayout } from "../components/AuthLayout";
import { AuthSubmitButton } from "../components/AuthSubmitButton";
import { AuthTextField } from "../components/AuthTextField";

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
      <main className="auth-loading-stage">
        <div className="auth-loading-spinner" />
        <p className="auth-loading-text">正在恢复登录状态…</p>
      </main>
    );
  }

  if (auth.status === "authenticated") {
    return <Navigate to={nextPath} replace state={loginSucceeded ? { loginSuccess: true } : undefined} />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const normalizedEmail = email.trim();
    const normalizedPassword = password.trim();

    if (!normalizedEmail) {
      setError("请输入邮箱地址");
      return;
    }

    if (!normalizedPassword) {
      setError("请输入密码");
      return;
    }

    setSubmitting(true);

    try {
      await auth.login({ email: normalizedEmail, password: normalizedPassword });
      setLoginSucceeded(true);
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "登录失败，请稍后重试");
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
              欢迎回到你的
              <br />
              口语练习通道
            </>
          }
          description="场景化英语口语陪练系统，基于真实场景开口练习，每轮结束获得简洁反馈与个人学习档案。"
        >
          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </div>
              <span className="auth-feature-item__text">上传场景图片</span>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
              </div>
              <span className="auth-feature-item__text">实时语音对话</span>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-item__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <span className="auth-feature-item__text">练习回顾与复盘</span>
            </div>
          </div>
        </AuthBrandPanel>
      }
    >
      <AuthFormCard title="登录账号" subtitle="继续你的英语口语练习">
        <form className="auth-form-modern" onSubmit={onSubmit}>
          <AuthTextField
            id="login-email"
            label="邮箱地址"
            type="email"
            placeholder="your@email.com"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          <AuthTextField
            id="login-password"
            label="密码"
            placeholder="••••••••"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            showPasswordToggle
          />
          {error ? <AuthAlert message={error} /> : null}
          <AuthSubmitButton submitting={submitting} submittingText="登录中…">
            登录
          </AuthSubmitButton>
          <div className="auth-form-footer">
            <button
              type="button"
              className="auth-form-link"
              onClick={() => navigate("/forgot-password", { state: { prefillEmail: email } })}
            >
              忘记密码？
            </button>
          </div>
        </form>

        <div className="auth-form-divider">
          <span className="auth-form-divider__text">还没有账号？</span>
        </div>
        <button type="button" className="auth-form-secondary" onClick={() => navigate("/register")}>
          创建新账号
        </button>
      </AuthFormCard>
    </AuthLayout>
  );
}
