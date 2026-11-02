import { FormEvent, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthLayout } from "../components/AuthLayout";
import { AuthLoadingStage, AuthTextButton } from "../components/AuthControls";
import { AuthSubmitButton } from "../components/AuthSubmitButton";
import { AuthTextField } from "../components/AuthTextField";
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
  const invalidLinkMessage = "重置链接已失效或已过期，请重新申请。";

  useEffect(() => {
    if (!success) {
      return;
    }

    const timerId = window.setTimeout(() => {
      navigate("/login", { replace: true });
    }, 1500);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [navigate, success]);

  if (auth.status === "refreshing") {
    return <AuthLoadingStage>正在恢复登录状态…</AuthLoadingStage>;
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

  const showRetryAction = !token || error === invalidLinkMessage;

  return (
    <AuthLayout
      brand={
        <AuthBrandPanel
          title={
            <>
              设置一个新的
              <br />
              登录密码
            </>
          }
          description="重置密码后，旧的 refresh 会话会被撤销。这样做的目的，是避免旧设备继续保留可用登录态。"
        />
      }
    >
      <AuthFormCard title="重置密码" subtitle="请输入一个包含字母和数字的新密码。">
        <form className="space-y-4" onSubmit={onSubmit}>
          <AuthTextField
            id="reset-password"
            label="新密码"
            placeholder="至少 6 个字符"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            showPasswordToggle
          />
          {error ? <AuthAlert message={error} /> : null}
          {success ? <AuthAlert variant="info" message="密码已更新，即将返回登录页。" /> : null}
          <AuthSubmitButton submitting={submitting} submittingText="提交中…">
            确认重置密码
          </AuthSubmitButton>
        </form>

        <div className="mt-5 flex flex-col items-center gap-3">
          {showRetryAction ? (
            <AuthTextButton onClick={() => navigate("/forgot-password")}>重新申请重置邮件</AuthTextButton>
          ) : null}
          <AuthTextButton onClick={() => navigate("/login")}>返回登录</AuthTextButton>
        </div>
      </AuthFormCard>
    </AuthLayout>
  );
}
