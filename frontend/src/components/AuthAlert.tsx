import { CircleAlert, CircleCheck } from "lucide-react";

type AuthAlertProps = {
  message: string;
  variant?: "error" | "info";
};

/** 表单内联提示：error 为错误（红），info 为中性/成功提示（绿）。 */
export function AuthAlert({ message, variant = "error" }: AuthAlertProps) {
  const isError = variant === "error";

  return (
    <p
      role="alert"
      className={`flex items-start gap-2 rounded-2xl border px-4 py-3 text-[13px] font-medium ${
        isError ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
      }`}
    >
      {isError ? (
        <CircleAlert size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      ) : (
        <CircleCheck size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      )}
      <span>{message}</span>
    </p>
  );
}
