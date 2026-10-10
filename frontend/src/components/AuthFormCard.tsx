import type { ReactNode } from "react";

type AuthFormCardProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
};

/** 右侧表单卡片外壳：标题 + 副标题 + 表单内容（毛玻璃卡片）。 */
export function AuthFormCard({ title, subtitle, children }: AuthFormCardProps) {
  return (
    <div className="auth-form-section">
      <div className="auth-form-section__card">
        <div className="auth-form-section__header">
          <h2 className="auth-form-section__title">{title}</h2>
          <p className="auth-form-section__subtitle">{subtitle}</p>
        </div>
        {children}
      </div>
    </div>
  );
}
