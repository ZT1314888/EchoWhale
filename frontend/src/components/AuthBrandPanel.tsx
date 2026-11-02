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

/** 左侧品牌栏：深色编辑页 + 品牌标 + 主标题 + 描述 + 可选列表，点击标识返回首页。 */
export function AuthBrandPanel({ title, description, children }: AuthBrandPanelProps) {
  const navigate = useNavigate();

  return (
    <div className="noise relative hidden overflow-hidden rounded-[32px] bg-[#131311] p-10 text-white lg:flex lg:flex-col">
      <div className="grid-pattern-light pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[#4f46e5]/40 blur-[110px]" />
      <div className="pointer-events-none absolute -bottom-28 -left-16 h-80 w-80 rounded-full bg-[#d8f34e]/15 blur-[110px]" />

      <button
        type="button"
        onClick={() => navigate("/")}
        aria-label="返回首页"
        className="relative flex w-fit items-center gap-3 text-left"
      >
        <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#d8f34e]">
          <Logo className="h-8 w-8" title="EchoWhale 品牌标志" />
        </span>
        <span className="font-display text-lg font-bold tracking-tight">EchoWhale</span>
      </button>

      <div className="relative mt-14">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#d8f34e]">
          Scene to conversation · 从场景到开口
        </p>
        <h2 className="font-display mt-4 text-[40px] font-bold leading-[1.04] tracking-tight">{title}</h2>
        <p className="mt-4 max-w-sm text-[13.5px] leading-relaxed text-white/60">{description}</p>
      </div>

      {children ? <div className="relative mt-10">{children}</div> : null}
    </div>
  );
}
