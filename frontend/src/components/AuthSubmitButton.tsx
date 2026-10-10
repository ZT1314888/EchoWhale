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
    <button type="submit" className="auth-form-submit" disabled={submitting}>
      {submitting ? (
        <>
          <span className="auth-form-submit__spinner" />
          <span>{submittingText}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}
