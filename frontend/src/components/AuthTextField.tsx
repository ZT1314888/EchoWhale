import { useState } from "react";

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

function EyeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

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

  return (
    <div className="auth-form-field">
      <label htmlFor={id} className="auth-form-field__label">
        {label}
      </label>
      {showPasswordToggle ? (
        <div className="auth-form-field__input-wrapper">
          <input
            id={id}
            type={inputType}
            className="auth-form-field__input"
            placeholder={placeholder}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            autoComplete={autoComplete}
          />
          <button
            type="button"
            className="auth-form-field__toggle"
            onClick={() => setVisible((current) => !current)}
            aria-label={visible ? "隐藏密码" : "显示密码"}
          >
            {visible ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      ) : (
        <input
          id={id}
          type={inputType}
          className="auth-form-field__input"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
        />
      )}
    </div>
  );
}
