type AuthAlertProps = {
  message: string;
  variant?: "error" | "info";
};

function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function SuccessIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

/** 表单内联提示：error 为错误（红），info 为中性/成功提示（绿）。 */
export function AuthAlert({ message, variant = "error" }: AuthAlertProps) {
  return (
    <div className={`auth-form-alert auth-form-alert--${variant}`} role="alert">
      {variant === "error" ? <AlertIcon /> : <SuccessIcon />}
      <span>{message}</span>
    </div>
  );
}
