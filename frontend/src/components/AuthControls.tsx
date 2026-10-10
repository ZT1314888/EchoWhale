import type { ReactNode } from "react";

type AuthTextButtonProps = {
  onClick: () => void;
  children: string;
};

/** 表单里的次级文字动作（忘记密码 / 重新申请重置邮件 / 返回登录）：无边框，靠字重区分。 */
export function AuthTextButton({ onClick, children }: AuthTextButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[12.5px] font-bold text-[#131311] underline decoration-[#d8f34e] decoration-2 underline-offset-4 transition hover:decoration-[#131311]"
    >
      {children}
    </button>
  );
}

/** 整行次级按钮：「创建新账号 / 立即登录 / 重新发送验证码」这类非提交动作。 */
export function AuthSecondaryButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-2xl border-2 border-[#131311]/10 bg-white px-5 py-3.5 text-[14px] font-bold text-[#131311] transition hover:border-[#131311] disabled:opacity-50"
    >
      {children}
    </button>
  );
}

/** 「分隔线 + 中间说明」的卡片页脚，登录/注册/找回三页共用。 */
export function AuthFormDivider({ label }: { label: string }) {
  return (
    <div className="mt-5 flex items-center gap-4">
      <span className="h-px flex-1 bg-[#131311]/10" />
      <span className="text-[12px] font-semibold text-stone-400">{label}</span>
      <span className="h-px flex-1 bg-[#131311]/10" />
    </div>
  );
}

/** 恢复登录态时的整页占位（登录/注册/找回共用）。 */
export function AuthLoadingStage({ children }: { children: ReactNode }) {
  return (
    <main className="grid min-h-[60vh] place-items-center">
      <div className="text-center">
        <span
          aria-hidden="true"
          className="mx-auto block h-8 w-8 animate-spin rounded-full border-[3px] border-[#131311]/15 border-t-[#131311]"
        />
        <p className="mt-4 text-[13px] font-semibold text-stone-500">{children}</p>
      </div>
    </main>
  );
}
