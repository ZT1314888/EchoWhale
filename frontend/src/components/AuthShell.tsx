import type { InputHTMLAttributes, ReactNode } from "react";
import { ArrowLeft, ChartLine, MessagesSquare, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { Logo } from "./Logo";

const HIGHLIGHTS = [
  { icon: Sparkles, en: "Real-scene coaching", cn: "真实场景扮演 · 每轮即时反馈" },
  { icon: MessagesSquare, en: "Speaking first, typing second", cn: "先开口再补充 · 语音与文字双通道" },
  { icon: ChartLine, en: "Reviews you can revisit", cn: "复盘存档 · 随时回看逐字稿" },
];

type AuthShellProps = {
  children: ReactNode;
  /** 主标题（英文），可访问名以它为准 */
  title: string;
  /** 次要语言副标题，渲染为 aria-hidden，不污染可访问名 */
  cn: string;
  desc: string;
};

/**
 * 账户类页面（登录/注册/验证/找回/重置）共用的整页外壳。
 *
 * 左侧是深色编辑页眉，右侧是表单卡片；`cn` 一律放进 aria-hidden 的 span ——
 * 测试用 `getByRole("heading", { name: "登录账号" })` 精确匹配主标题，双语
 * 拼接会把可访问名变成「登录账号 登录」而全部失配。
 */
export function AuthShell({ children, title, cn, desc }: AuthShellProps) {
  return (
    <div className="mx-auto grid min-h-[86vh] max-w-6xl items-stretch gap-5 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr]">
      <div className="noise relative hidden overflow-hidden rounded-[32px] bg-[#131311] p-10 text-white lg:flex lg:flex-col">
        <div className="grid-pattern-light pointer-events-none absolute inset-0" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[#4f46e5]/40 blur-[110px]" />
        <div className="pointer-events-none absolute -bottom-28 -left-16 h-80 w-80 rounded-full bg-[#d8f34e]/15 blur-[110px]" />

        <div className="relative flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#d8f34e]">
              <Logo className="h-8 w-8" title="EchoWhale 品牌标志" />
            </span>
            <span className="font-display text-lg font-bold tracking-tight">EchoWhale</span>
          </Link>
          <span className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] text-white/60">
            Voice practice
          </span>
        </div>

        <div className="relative mt-14">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#d8f34e]">
            From a photo to a conversation
          </p>
          <h2 className="font-display mt-4 text-[44px] font-bold leading-[1.02] tracking-tight">
            Look at a scene.
            <br />
            Then <span className="font-serif-accent font-medium text-gradient">say it out loud.</span>
          </h2>
          <p className="mt-4 max-w-sm text-[13.5px] leading-relaxed text-white/60">
            Upload one everyday photo, and EchoWhale turns it into a role-play you can speak through.
            一张生活照片，就能开口练一轮。
          </p>
        </div>

        <div className="relative mt-10 space-y-3">
          {HIGHLIGHTS.map(({ icon: Icon, en, cn: cnLabel }) => (
            <div key={en} className="flex items-center gap-3.5 rounded-2xl border border-white/10 bg-white/[0.05] p-3.5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/10 text-[#d8f34e]">
                <Icon size={17} />
              </span>
              <span>
                <span className="block text-[13.5px] font-bold">{en}</span>
                <span className="block text-[11.5px] text-white/50">{cnLabel}</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center">
        <div className="w-full rounded-[32px] border border-[#131311]/8 bg-[#faf9f6] p-8 shadow-[0_32px_64px_-32px_rgba(19,19,17,0.25)] sm:p-10">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-stone-400 transition hover:text-[#131311]"
          >
            <ArrowLeft size={14} aria-hidden="true" />
            Back to home
            <span aria-hidden="true">返回首页</span>
          </Link>
          <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.2em] text-[#4f46e5]">Account · 账户</p>
          <h1 className="font-display mt-2 text-[30px] font-bold tracking-tight">
            {title}
            <span aria-hidden="true" className="font-serif-accent ml-2 align-middle text-[0.6em] font-medium text-stone-400">
              {cn}
            </span>
          </h1>
          <p className="mt-2 text-[13.5px] leading-relaxed text-stone-500">{desc}</p>
          <div className="mt-7">{children}</div>
          <p className="mt-6 flex items-center justify-center gap-1.5 text-[11.5px] text-stone-400">
            <ShieldCheck size={13} aria-hidden="true" /> Encrypted &amp; private · 数据加密，安心使用
          </p>
        </div>
      </div>
    </div>
  );
}

/** 深色圆角字段，标签沿用中文以维持既有 getByLabelText 契约。 */
export function Field({ label, cn, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; cn?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-bold text-[#131311]">
        {label}
        {cn && <span className="font-normal text-stone-400">{cn}</span>}
      </span>
      <input
        {...props}
        className="w-full rounded-2xl border border-[#131311]/12 bg-white px-4 py-3 text-[14px] font-medium outline-none transition placeholder:font-normal placeholder:text-stone-400 focus:border-[#131311] focus:ring-4 focus:ring-[#131311]/5"
      />
    </label>
  );
}

/** 主提交按钮：loading 时禁用并显示 spinner，文案由调用方切换。 */
export function PrimaryButton({ children, loading }: { children: ReactNode; loading?: boolean }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="group relative w-full overflow-hidden rounded-2xl bg-[#131311] px-5 py-[15px] text-[14px] font-bold text-white shadow-xl transition hover:bg-black disabled:opacity-60"
    >
      <span className="relative z-10 inline-flex items-center justify-center gap-2">
        {loading && (
          <span
            aria-hidden="true"
            className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
          />
        )}
        {children}
      </span>
      <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/10 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
    </button>
  );
}
