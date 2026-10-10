import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Logo } from "./Logo";

type AuthBrandPanelProps = {
  /** 主标题，可用 <br /> 手动换行以对齐设计稿 */
  title: ReactNode;
  description: string;
  /** 标题下方的特性/说明列表（可选） */
  children?: ReactNode;
};

/** 左侧品牌栏：品牌标识 + 主标题 + 描述 + 可选列表，点击标识返回首页。 */
export function AuthBrandPanel({ title, description, children }: AuthBrandPanelProps) {
  const navigate = useNavigate();

  return (
    <div className="auth-brand-section">
      <button
        className="auth-brand-section__logo-link"
        onClick={() => navigate("/")}
        type="button"
        aria-label="返回首页"
      >
        <div className="auth-brand-section__logo-wrapper">
          <Logo className="auth-brand-section__logo" />
        </div>
        <h2 className="auth-brand-section__wordmark">EchoWhale</h2>
      </button>

      <div className="auth-brand-section__content">
        <h1 className="auth-brand-section__title">{title}</h1>
        <p className="auth-brand-section__description">{description}</p>
        {children}
      </div>
    </div>
  );
}
