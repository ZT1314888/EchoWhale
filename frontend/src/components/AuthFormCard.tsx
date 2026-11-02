import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";

type AuthFormCardProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
};

/**
 * 右侧表单卡片：账户页眉 + 主标题 + 副标题 + 表单内容。
 *
 * 卡片标题是 h1 —— 路由级测试用 `getByRole("heading", { name: "登录账号" })`
 * 精确匹配，标题里不放任何次要语言文本。
 */
export function AuthFormCard({ title, subtitle, children }: AuthFormCardProps) {
  return (
    <div className="flex items-center">
      <div className="w-full rounded-[32px] border border-[#131311]/8 bg-[#faf9f6] p-8 shadow-[0_32px_64px_-32px_rgba(19,19,17,0.25)] sm:p-10">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#4f46e5]">Account · 账户</p>
        <h1 className="font-display mt-2 text-[30px] font-bold tracking-tight">{title}</h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-stone-500">{subtitle}</p>
        <div className="mt-7">{children}</div>
        <p className="mt-6 flex items-center justify-center gap-1.5 text-[11.5px] text-stone-400">
          <ShieldCheck size={13} aria-hidden="true" />
          Encrypted &amp; private
          <span aria-hidden="true">· 数据加密，安心使用</span>
        </p>
      </div>
    </div>
  );
}
