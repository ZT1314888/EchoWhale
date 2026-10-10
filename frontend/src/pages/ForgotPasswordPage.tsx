import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Clock3, MailCheck, ShieldCheck } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFeatureList } from "../components/AuthFeatureList";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthFormDivider, AuthLoadingStage, AuthSecondaryButton } from "../components/AuthControls";
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
    return <AuthLoadingStage>正在恢复登录状态…</AuthLoadingStage>;
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
          description="输入注册邮箱，我们会发送密码重置链接。无论邮箱是否注册，页面都给出相同提示，以免泄露账号是否存在。"
        >
          <AuthFeatureList
            items={[
              { icon: Clock3, text: "重置链接有效期有限，请尽快使用" },
              { icon: ShieldCheck, text: "重置成功后旧登录会话会被撤销" },
              { icon: MailCheck, text: "没收到邮件？请检查垃圾邮件文件夹" },
            ]}
          />
        </AuthBrandPanel>
      }
    >
      <AuthFormCard title="忘记密码" subtitle="输入注册邮箱，接收密码重置链接">
        <form className="space-y-4" onSubmit={onSubmit}>
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

        <AuthFormDivider label="想起密码了？" />
        <AuthSecondaryButton onClick={() => navigate("/login", { state: { prefillEmail: email } })}>
          返回登录
        </AuthSecondaryButton>
      </AuthFormCard>
    </AuthLayout>
  );
}
