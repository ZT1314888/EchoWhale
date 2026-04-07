import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
import { resendVerification, verifyEmail } from "../services/authApi";

type VerificationState = "ready" | "sending" | "sent" | "verifying" | "verified" | "error";

export function VerifyEmailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const token = params.get("token") ?? "";
  const email = params.get("email") ?? "";
  const [state, setState] = useState<VerificationState>(token ? "verifying" : "ready");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    setState("verifying");
    setError("");
    verifyEmail(token)
      .then(() => {
        if (!cancelled) {
          setState("verified");
        }
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        const typed = reason as { message?: string };
        setError(typed.message ?? "邮箱验证失败，请稍后重试。");
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onResend() {
    if (!email) {
      setError("缺少邮箱地址，无法重新发送验证邮件。");
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
      setError(typed.message ?? "验证邮件发送失败，请稍后重试。");
      setState("error");
    }
  }

  const title =
    state === "verified"
      ? "邮箱验证完成"
      : token
        ? "正在验证邮箱…"
        : "查收你的验证邮件";
  const description =
    state === "verified"
      ? "你的账号已经激活，现在可以返回登录并继续练习。"
      : token
        ? "我们正在确认这封邮件属于你。"
        : "注册已完成。为了保护账号安全，请先完成邮箱验证，再进入登录。";

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

            {!token && email ? <p className="muted-text">验证邮件已发送到：{email}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
            {state === "sent" ? <p className="muted-text">新的验证邮件已经发出，请检查收件箱和垃圾邮件。</p> : null}

            {!token && state !== "verified" ? (
              <button className="primary-button" type="button" disabled={state === "sending"} onClick={onResend}>
                {state === "sending" ? "发送中…" : "重新发送验证邮件"}
              </button>
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
