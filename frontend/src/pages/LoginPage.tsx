import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { FileUp, MessagesSquare, Sparkles } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFeatureList } from "../components/AuthFeatureList";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthFormDivider, AuthLoadingStage, AuthSecondaryButton, AuthTextButton } from "../components/AuthControls";
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
    return <AuthLoadingStage>正在恢复登录状态…</AuthLoadingStage>;
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
          description="场景化英语口语陪练系统。上传一张日常照片，EchoWhale 把它变成可以直接开口的角色对话，每轮结束都有复盘存档。"
        >
          <AuthFeatureList
            items={[
              { icon: FileUp, text: "上传场景图片，自动生成角色对话" },
              { icon: MessagesSquare, text: "实时语音与文字双通道练习" },
              { icon: Sparkles, text: "每轮结束获得可操作的复盘反馈" },
            ]}
          />
        </AuthBrandPanel>
      }
    >
      <AuthFormCard title="登录账号" subtitle="继续你的英语口语练习">
        <form className="space-y-4" onSubmit={onSubmit}>
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
          <div className="flex justify-end">
            <AuthTextButton onClick={() => navigate("/forgot-password", { state: { prefillEmail: email } })}>
              忘记密码？
            </AuthTextButton>
          </div>
          {error ? <AuthAlert message={error} /> : null}
          <AuthSubmitButton submitting={submitting} submittingText="登录中…">
            登录
          </AuthSubmitButton>
        </form>

        <AuthFormDivider label="还没有账号？" />
        <AuthSecondaryButton onClick={() => navigate("/register")}>创建新账号</AuthSecondaryButton>
      </AuthFormCard>
    </AuthLayout>
  );
}
