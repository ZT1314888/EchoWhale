import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { AuthAlert } from "../components/AuthAlert";
import { AuthBenefitList } from "../components/AuthFeatureList";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthFormDivider, AuthLoadingStage, AuthSecondaryButton } from "../components/AuthControls";
import { AuthLayout } from "../components/AuthLayout";
import { AuthSubmitButton } from "../components/AuthSubmitButton";
import { AuthTextField } from "../components/AuthTextField";

const BENEFITS = [
  { title: "场景化练习", desc: "上传场景图片，系统识别场景并生成可直接开口的角色对话" },
  { title: "实时反馈", desc: "每轮对话结束后得到简洁、可操作的学习建议" },
  { title: "学习档案", desc: "练习记录自动沉淀，在练习历史与进度页随时回看" },
];

export function RegisterPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const [nickname, setNickname] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const nextPath = new URLSearchParams(location.search).get("next") || "/history";

  if (auth.status === "refreshing") {
    return <AuthLoadingStage>正在恢复登录状态…</AuthLoadingStage>;
  }

  if (auth.status === "authenticated") {
    return <Navigate to={nextPath} replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const normalizedNickname = nickname.trim();
    const normalizedEmail = email.trim();
    const normalizedPassword = password.trim();

    if (!normalizedNickname) {
      setError("请输入昵称");
      return;
    }

    if (!normalizedEmail) {
      setError("请输入邮箱地址");
      return;
    }

    if (!normalizedPassword) {
      setError("请输入密码");
      return;
    }

    if (normalizedPassword.length < 6) {
      setError("密码长度至少为 6 个字符");
      return;
    }

    if (normalizedPassword !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    setSubmitting(true);

    try {
      await auth.register({
        nickname: normalizedNickname,
        email: normalizedEmail,
        password: normalizedPassword,
      });
      navigate(
        {
          pathname: "/verify-email",
          search: `?email=${encodeURIComponent(normalizedEmail)}`,
        },
        {
          replace: true,
        },
      );
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "注册失败，请稍后重试");
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
              开始你的
              <br />
              口语练习之旅
            </>
          }
          description="创建账号，保存每一轮练习回响。从一张场景图片开始，用实时语音对话把口语练起来。"
        >
          <AuthBenefitList items={BENEFITS} />
        </AuthBrandPanel>
      }
    >
      <AuthFormCard title="创建账号" subtitle="注册后即可保存练习记录">
        <form className="space-y-4" onSubmit={onSubmit}>
          <AuthTextField
            id="register-nickname"
            label="昵称"
            placeholder="输入你的昵称"
            value={nickname}
            onChange={setNickname}
            autoComplete="name"
          />
          <AuthTextField
            id="register-email"
            label="邮箱地址"
            type="email"
            placeholder="your@email.com"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          <AuthTextField
            id="register-password"
            label="密码"
            placeholder="至少 6 个字符"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            showPasswordToggle
          />
          <AuthTextField
            id="register-confirm-password"
            label="确认密码"
            placeholder="再次输入密码"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            showPasswordToggle
          />
          {error ? <AuthAlert message={error} /> : null}
          <AuthSubmitButton submitting={submitting} submittingText="创建中…">
            创建账号
          </AuthSubmitButton>
        </form>

        <AuthFormDivider label="已有账号？" />
        <AuthSecondaryButton onClick={() => navigate("/login")}>立即登录</AuthSecondaryButton>
      </AuthFormCard>
    </AuthLayout>
  );
}
