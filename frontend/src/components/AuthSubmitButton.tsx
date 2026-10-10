import type { ReactNode } from "react";

type AuthSubmitButtonProps = {
  submitting: boolean;
  submittingText?: string;
  children: ReactNode;
};

/** 提交按钮：提交中显示旋转指示与等待文案，禁用交互。 */
export function AuthSubmitButton({
  submitting,
  submittingText = "提交中…",
  children,
}: AuthSubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={submitting}
      className="group relative w-full overflow-hidden rounded-2xl bg-[#131311] px-5 py-[15px] text-[14px] font-bold text-white shadow-xl transition hover:bg-black disabled:opacity-60"
    >
      <span className="relative z-10 inline-flex items-center justify-center gap-2">
        {submitting ? (
          <>
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
            />
            {submittingText}
          </>
        ) : (
          children
        )}
      </span>
      <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/10 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
    </button>
  );
}
