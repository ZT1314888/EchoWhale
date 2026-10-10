import type { LucideIcon } from "lucide-react";

export type AuthFeatureItem = { icon: LucideIcon; text: string };

/** 左侧品牌栏的图标条目列表：条目由各页面给出，都是 EchoWhale 真实具备的能力。 */
export function AuthFeatureList({ items }: { items: AuthFeatureItem[] }) {
  return (
    <div className="space-y-3">
      {items.map(({ icon: Icon, text }) => (
        <div
          key={text}
          className="flex items-center gap-3.5 rounded-2xl border border-white/10 bg-white/[0.05] p-3.5"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/10 text-[#d8f34e]">
            <Icon size={17} aria-hidden="true" />
          </span>
          <span className="text-[13.5px] font-bold">{text}</span>
        </div>
      ))}
    </div>
  );
}

/** 左侧品牌栏的编号条目列表（注册页）。 */
export function AuthBenefitList({ items }: { items: { title: string; desc: string }[] }) {
  return (
    <div className="space-y-4">
      {items.map((item, index) => (
        <div key={item.title} className="flex gap-4">
          <span className="font-display text-[13px] font-bold text-[#d8f34e]">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span>
            <span className="block text-[13.5px] font-bold">{item.title}</span>
            <span className="block text-[11.5px] leading-relaxed text-white/50">{item.desc}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** 表单卡片底部的「分隔线 + 次级整行按钮」，登录/注册/找回三页共用。 */
export function AuthFormDivider({ label }: { label: string }) {
  return (
    <div className="mt-4 flex items-center gap-4">
      <span className="h-px flex-1 bg-[#131311]/10" />
      <span className="text-[12px] font-semibold text-stone-400">{label}</span>
      <span className="h-px flex-1 bg-[#131311]/10" />
    </div>
  );
}

/** 整行次级按钮：用于「创建新账号 / 立即登录 / 返回登录」这类非提交动作。 */
export function AuthSecondaryButton({ onClick, children }: { onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-3 w-full rounded-2xl border-2 border-[#131311]/10 bg-white px-5 py-3.5 text-[14px] font-bold text-[#131311] transition hover:border-[#131311]"
    >
      {children}
    </button>
  );
}
