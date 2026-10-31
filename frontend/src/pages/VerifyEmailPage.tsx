import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { MailCheck, MailOpen } from "lucide-react";

import { AuthAlert } from "../components/AuthAlert";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthSecondaryButton, AuthTextButton } from "../components/AuthControls";
import { AuthFormCard } from "../components/AuthFormCard";
import { AuthLayout } from "../components/AuthLayout";
import { AuthSubmitButton } from "../components/AuthSubmitButton";
import { AuthTextField } from "../components/AuthTextField";
import { resendVerification, verifyEmail } from "../services/authApi";

type VerificationState = "ready" | "sending" | "sent" | "verifying" | "verified" | "error";

export function VerifyEmailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const email = params.get("email") ?? "";
  const [code, setCode] = useState("");
  const [state, setState] = useState<VerificationState>("ready");
  const [error, setError] = useState("");

  async function onResend() {
    if (!email) {
      setError("缺少邮箱地址，无法重新发送验证码。");
      setState("error");
      return;
    }

    setState("sending");
    setError("");
    try {
      await resendVerification({ email });
      setState("sent");
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "验证码发送失败，请稍后重试。");
      setState("error");
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email) {
      setError("缺少邮箱地址，无法完成验证。");
      setState("error");
      return;
    }
    if (!code.trim()) {
      setError("验证码不能为空");
      setState("error");
      return;
    }

    setState("verifying");
    setError("");
    try {
      await verifyEmail({ email, code: code.trim() });
      setState("verified");
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "邮箱验证失败，请稍后重试。");
      setState("error");
    }
  }

  const verified = state === "verified";
  const title = verified ? "邮箱验证完成" : "查收你的验证码";
  const description = verified
    ? "你的账号已经激活，现在可以返回登录并继续练习。"
    : "注册已完成。请输入邮件中的 6 位验证码，完成账号激活。";

  return (
    <AuthLayout
      brand={
        <AuthBrandPanel
          title={
            <>
              先完成邮箱验证
              <br />
              再继续保存练习回响
            </>
          }
          description="这一步的目的，是确保账号可恢复、可找回，也避免别人冒用你的邮箱创建账号。"
        />
      }
    >
      <AuthFormCard title={title} subtitle={description}>
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-[22px] bg-[#131311] text-[#d8f34e]">
          {verified ? <MailCheck size={26} aria-hidden="true" /> : <MailOpen size={26} aria-hidden="true" />}
        </div>

        <div className="mt-5 space-y-3">
          {email ? <p className="text-center text-[13px] text-stone-500">验证码已发送到：{email}</p> : null}
          {error ? <AuthAlert message={error} /> : null}
          {state === "sent" ? (
            <AuthAlert variant="info" message="新的验证码已经发出，请检查收件箱和垃圾邮件。" />
          ) : null}
        </div>

        {!verified ? (
          <form className="mt-5 space-y-4" onSubmit={onSubmit}>
            <AuthTextField
              id="verify-email-code"
              label="验证码"
              placeholder="6 位数字验证码"
              value={code}
              onChange={setCode}
            />
            <AuthSubmitButton submitting={state === "verifying"} submittingText="验证中…">
              完成验证
            </AuthSubmitButton>
          </form>
        ) : null}

        <div className="mt-5 space-y-3">
          {!verified ? (
            <AuthSecondaryButton onClick={onResend} disabled={state === "sending"}>
              {state === "sending" ? "发送中…" : "重新发送验证码"}
            </AuthSecondaryButton>
          ) : null}
          <div className="flex justify-center">
            <AuthTextButton onClick={() => navigate("/login", { state: { prefillEmail: email } })}>
              返回登录
            </AuthTextButton>
          </div>
        </div>
      </AuthFormCard>
    </AuthLayout>
  );
}
