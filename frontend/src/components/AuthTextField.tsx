import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

type AuthTextFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "email";
  placeholder?: string;
  autoComplete?: string;
  /** 为 true 时渲染密码可见性切换按钮，输入框固定为密码态 */
  showPasswordToggle?: boolean;
};

/** 表单输入字段：标签 + 输入框，密码字段自带可见性切换。 */
export function AuthTextField({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
  showPasswordToggle = false,
}: AuthTextFieldProps) {
  const [visible, setVisible] = useState(false);
  const inputType = showPasswordToggle ? (visible ? "text" : "password") : type;

  const inputClassName =
    "w-full rounded-2xl border border-[#131311]/12 bg-white px-4 py-3 text-[14px] font-medium outline-none transition placeholder:font-normal placeholder:text-stone-400 focus:border-[#131311] focus:ring-4 focus:ring-[#131311]/5";

  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-bold text-[#131311]">{label}</span>
      {showPasswordToggle ? (
        <span className="relative block">
          <input
            id={id}
            type={inputType}
            className={`${inputClassName} pr-12`}
            placeholder={placeholder}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            autoComplete={autoComplete}
          />
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            aria-label={visible ? "隐藏密码" : "显示密码"}
            className="absolute right-2 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-[#131311]"
          >
            {visible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
          </button>
        </span>
      ) : (
        <input
          id={id}
          type={inputType}
          className={inputClassName}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
        />
      )}
    </label>
  );
}
