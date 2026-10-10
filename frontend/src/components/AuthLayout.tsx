import type { ReactNode } from "react";

type AuthLayoutProps = {
  /** 左侧品牌栏内容（AuthBrandPanel） */
  brand: ReactNode;
  /** 右侧表单栏内容（AuthFormCard） */
  children: ReactNode;
};

/** 登录/注册/找回密码共用的整页外壳：编辑感双栏，窄屏收成单列。 */
export function AuthLayout({ brand, children }: AuthLayoutProps) {
  return (
    <div className="mx-auto grid min-h-[86vh] max-w-6xl items-stretch gap-5 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr]">
      {brand}
      {children}
    </div>
  );
}
