import { Link } from "react-router-dom";

import { Logo } from "./Logo";

export function BrandHeader() {
  return (
    <header className="app-brand-header">
      <Link className="brand-lockup" to="/">
        <span className="brand-mark">
          <Logo className="h-12 w-12" title="EchoWhale 品牌标志" />
        </span>
        <span className="brand-wordmark">EchoWhale</span>
      </Link>

      <nav className="brand-actions" aria-label="主导航">
        <Link className="ghost-button" to="/history">
          历史记录
        </Link>
        <Link className="ghost-button" to="/login">
          登录 / 注册
        </Link>
      </nav>
    </header>
  );
}
