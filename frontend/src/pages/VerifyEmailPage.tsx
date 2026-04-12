import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
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

  const title =
    state === "verified"
      ? "邮箱验证完成"
      : "查收你的验证码";
  const description =
    state === "verified"
      ? "你的账号已经激活，现在可以返回登录并继续练习。"
      : "注册已完成。请输入邮件中的 6 位验证码，完成账号激活。";

  return (
    <div className="page-shell page-shell--auth">
      <div className="page-frame">
        <BrandHeader />

        <main className="auth-layout">
          <section className="panel-card auth-aside">
            <p className="eyebrow eyebrow--brand">EchoWhale</p>
            <h2>先完成邮箱验证，再继续保存练习回响</h2>
            <p className="muted-text">这一步的目的，是确保账号可恢复、可找回，也避免别人冒用你的邮箱创建账号。</p>
          </section>

          <section className="panel-card auth-panel auth-panel--rounded">
            <div className="section-header section-header--stack">
              <p className="eyebrow">Verify Email</p>
              <h1>{title}</h1>
              <p className="muted-text">{description}</p>
            </div>

            {email ? <p className="muted-text">验证码已发送到：{email}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
            {state === "sent" ? <p className="muted-text">新的验证码已经发出，请检查收件箱和垃圾邮件。</p> : null}

            {state !== "verified" ? (
              <form className="auth-form" onSubmit={onSubmit}>
                <label className="field-label" htmlFor="verify-email-code">
                  验证码
                </label>
                <input
                  id="verify-email-code"
                  className="input-field"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
                <button className="primary-button primary-button--aqua" type="submit" disabled={state === "verifying"}>
                  {state === "verifying" ? "验证中…" : "完成验证"}
                </button>
                <button className="primary-button" type="button" disabled={state === "sending"} onClick={onResend}>
                  {state === "sending" ? "发送中…" : "重新发送验证码"}
                </button>
              </form>
            ) : null}

            <button className="link-button" type="button" onClick={() => navigate("/login", { state: { prefillEmail: email } })}>
              返回登录
            </button>
          </section>
        </main>
      </div>
    </div>
  );
}
