import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";
import { register } from "../services/mockApi";

export function RegisterPage() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState("Echo Learner");
  const [email, setEmail] = useState("name@example.com");
  const [password, setPassword] = useState("secret123");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await register({ nickname, email, password });
      navigate("/history");
    } catch (reason) {
      const typed = reason as { message?: string };
      setError(typed.message ?? "注册失败，请稍后重试。");
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
            <h2>保存每一轮练习回响</h2>
            <p className="muted-text">创建账号后，你可以保存场景、回看回响，并从下一轮语音练习继续。</p>
            <div className="pill-row">
              <span className="info-pill">场景上传</span>
              <span className="info-pill">复盘留存</span>
            </div>
          </section>

          <section className="panel-card auth-panel auth-panel--rounded">
            <div className="section-header section-header--stack">
              <p className="eyebrow">Register</p>
              <h1>创建你的开口通道</h1>
              <p className="muted-text">注册后即可保存练习记录，随时回看每一轮回响。</p>
            </div>

            <form className="auth-form" onSubmit={onSubmit}>
              <label className="field-label" htmlFor="register-nickname">
                昵称
              </label>
              <input
                id="register-nickname"
                className="input-field"
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
              />
              <label className="field-label" htmlFor="register-email">
                邮箱
              </label>
              <input
                id="register-email"
                className="input-field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <label className="field-label" htmlFor="register-password">
                密码
              </label>
              <input
                id="register-password"
                className="input-field"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {error ? <p className="form-error">{error}</p> : null}
              <button className="primary-button primary-button--aqua" type="submit" disabled={submitting}>
                {submitting ? "创建中…" : "创建账号"}
              </button>
            </form>

            <p className="muted-text">已经有账号了？登录后，从上次鲸鱼停下来的那句继续。</p>
            <button className="link-button" type="button" onClick={() => navigate("/login")}>
              去登录
            </button>
          </section>
        </main>
      </div>
    </div>
  );
}
