import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { SampleSceneCard } from "../components/SampleSceneCard";
import { UserMenu } from "../components/UserMenu";
import { sampleScenes } from "../data/mockApp";

function validateImage(file: File) {
  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];

  if (!allowedTypes.includes(file.type)) {
    return "请上传 JPG、PNG 或 WebP 图片。";
  }

  if (file.size > 10 * 1024 * 1024) {
    return "图片需要小于 10 MB。";
  }

  return null;
}

const LOGIN_SUCCESS_TOAST_MS = 2500;

export function HomeUploadPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [error, setError] = useState("");
  const [showLoginSuccess, setShowLoginSuccess] = useState(
    Boolean((location.state as { loginSuccess?: boolean } | null)?.loginSuccess),
  );

  useEffect(() => {
    const routeState = location.state as { loginSuccess?: boolean } | null;
    if (!routeState?.loginSuccess) {
      return;
    }

    setShowLoginSuccess(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

  useEffect(() => {
    if (!showLoginSuccess) {
      return;
    }

    const timerId = window.setTimeout(() => {
      setShowLoginSuccess(false);
    }, LOGIN_SUCCESS_TOAST_MS);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [showLoginSuccess]);

  function startFromSample(sampleSceneId: string) {
    navigate("/session/loading", {
      state: { draft: { source: "sample", sampleSceneId } },
    });
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const validationMessage = validateImage(file);

    if (validationMessage) {
      setError(validationMessage);
      setSelectedFileName("");
      return;
    }

    setError("");
    setSelectedFileName(file.name);
    navigate("/session/loading", {
      state: { draft: { source: "file", fileName: file.name, file } },
    });
  }

  return (
    <div className="page-shell page-shell--home">
      <div className="page-frame">
        <header className="home-topbar">
          <span aria-hidden="true" className="home-topbar-spacer" />
          <Link className="home-wordmark" to="/">
            EchoWhale
          </Link>
          {auth.status === "authenticated" ? (
            <UserMenu variant="home" />
          ) : (
            <Link className="home-auth-link" to="/login">
              登录 / 注册
            </Link>
          )}
        </header>

        {showLoginSuccess ? (
          <section className="success-toast" role="status" aria-live="polite">
            <div>
              <p className="success-toast__eyebrow">登录成功</p>
              <p className="success-toast__text">已成功登录，欢迎回来。</p>
            </div>
            <button
              className="success-toast__close"
              type="button"
              aria-label="关闭登录成功提示"
              onClick={() => setShowLoginSuccess(false)}
            >
              关闭提示
            </button>
          </section>
        ) : null}

        <main className="home-stage">
          <section className="home-upload-card">
            <p className="eyebrow eyebrow--brand">从这里开始</p>
            <h1 className="home-title">上传一个场景，马上开口练习。</h1>
            <p className="home-intro">
              拖入一张生活图片，让 EchoWhale 把它整理成一轮安静、专注的口语练习。
            </p>

            <button className="dropzone-card dropzone-card--home" type="button" onClick={() => inputRef.current?.click()}>
              <span className="dropzone-title">点击上传，或把图片拖到这里</span>
              <span className="muted-text">
                支持 JPG / PNG，最大 10 MB。我们会先读场景、定角色，再准备第一句开场提示。
              </span>
              {selectedFileName ? <span className="upload-state">{selectedFileName}</span> : null}
              {error ? <span className="form-error">{error}</span> : null}
            </button>

            <div className="home-cta-row">
              <button className="primary-button" type="button" onClick={() => inputRef.current?.click()}>
                选择图片
              </button>
              <button className="ghost-button ghost-button--home" type="button" onClick={() => startFromSample("coffee")}>
                使用示例场景
              </button>
            </div>

            <input
              ref={inputRef}
              className="sr-only"
              type="file"
              aria-label="点击上传，或把图片拖到这里"
              accept="image/jpeg,image/png,image/webp"
              onChange={onFileChange}
            />
          </section>

          <section className="home-samples">
            <h2 className="home-samples-title">试试一个示例场景</h2>
            <div className="home-sample-grid">
              {sampleScenes.map((scene) => (
                <SampleSceneCard key={scene.id} scene={scene} onSelect={startFromSample} />
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

