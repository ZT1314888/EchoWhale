import type { ReactNode } from "react";

type AuthLayoutProps = {
  /** 左侧品牌栏内容（AuthBrandPanel） */
  brand: ReactNode;
  /** 右侧表单栏内容（AuthFormCard） */
  children: ReactNode;
};

/** 登录/注册/找回密码共用的整页外壳：渐变底 + 左右两栏居中布局。 */
export function AuthLayout({ brand, children }: AuthLayoutProps) {
  return (
    <div className="auth-page">
      <div className="auth-page__container">
        {brand}
        {children}
      </div>
    </div>
  );
}
