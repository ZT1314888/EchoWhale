import { useEffect, useState } from "react";
import { ArrowUpRight, History, LogOut, Menu, Mic, TrendingUp, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Logo } from "./Logo";

/**
 * 中心导航的三个入口。`match` 是「哪些路径算这个入口的激活态」，与后端无关，
 * 只为把 `/session/*` 归到练习、`/session/:id/review` 归到历史。
 */
const LINKS = [
  { to: "/", label: "Practice", cn: "练习", icon: Mic, match: ["/", "/session"] },
  { to: "/history", label: "Library", cn: "历史", icon: History, match: ["/history"] },
  { to: "/progress", label: "Progress", cn: "进度", icon: TrendingUp, match: ["/progress"] },
];

/** 这些路由属于「账户」流程，原型在此隐藏中心导航，让表单成为唯一焦点。 */
const AUTH_ROUTES = ["/login", "/register", "/verify-email", "/forgot-password", "/reset-password"];

function isActive(pathname: string, match: string[]) {
  return match.some((prefix) => (prefix === "/" ? pathname === "/" : pathname.startsWith(prefix)));
}

export function Navbar() {
  const auth = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const onAuthRoute = AUTH_ROUTES.some((route) => location.pathname.startsWith(route));
  const user = auth.user;

  return (
    <header
      className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled ? "bg-[#f4f3ef]/85 glass shadow-[0_1px_0_0_rgba(19,19,17,0.08)]" : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link to="/" className="group flex items-center gap-3">
          <span className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-2xl bg-[#131311] shadow-lg transition-transform duration-300 group-hover:rotate-6">
            <Logo className="h-8 w-8" title="EchoWhale 品牌标志" />
          </span>
          <span className="leading-none">
            <span className="font-display block text-[19px] font-bold tracking-tight">EchoWhale</span>
            <span className="mt-1 block text-[10.5px] font-medium uppercase tracking-[0.14em] text-stone-500">
              AI Speaking Coach
            </span>
          </span>
        </Link>

        {!onAuthRoute && (
          <nav
            aria-label="主导航"
            className="hidden items-center gap-1 rounded-full border border-[#131311]/10 bg-white/70 p-1.5 glass md:flex"
          >
            {LINKS.map((link) => {
              const active = isActive(location.pathname, link.match);
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-[13.5px] font-semibold transition-all duration-200 ${
                    active ? "bg-[#131311] text-white shadow-md" : "text-stone-500 hover:bg-[#131311]/5 hover:text-[#131311]"
                  }`}
                >
                  <link.icon size={15} strokeWidth={2.2} />
                  {link.label}
                  {/* 次要语言文本必须 aria-hidden：否则可访问名会变成 "Practice练习"，精确匹配的断言全部失效。 */}
                  <span aria-hidden="true" className={`text-[11px] font-normal ${active ? "text-white/60" : "text-stone-400"}`}>
                    {link.cn}
                  </span>
                </Link>
              );
            })}
          </nav>
        )}

        <div className="hidden items-center gap-2.5 md:flex">
          {user ? (
            <>
              <Link
                to="/progress"
                className="group flex items-center gap-2.5 rounded-full border border-[#131311]/10 bg-white/80 py-1.5 pl-1.5 pr-4 transition hover:border-[#131311]/25 glass"
              >
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 place-items-center rounded-full bg-[#131311] text-[13px] font-bold text-[#d8f34e]"
                >
                  {user.nickname.slice(0, 1).toUpperCase()}
                </span>
                <span className="max-w-[100px] truncate text-[13.5px] font-semibold">{user.nickname}</span>
              </Link>
              {/* 登出是同级图标按钮而非下拉菜单项：少一层 hover/focus 状态机，也少一处 DOM 结构耦合。 */}
              <button
                type="button"
                onClick={() => void auth.logout()}
                aria-label="退出登录"
                title="退出登录"
                className="grid h-10 w-10 place-items-center rounded-full border border-[#131311]/10 bg-white/80 text-stone-500 transition hover:bg-[#131311] hover:text-white"
              >
                <LogOut size={16} />
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-full px-4 py-2.5 text-[13.5px] font-semibold text-stone-600 transition hover:bg-[#131311]/5 hover:text-[#131311]"
              >
                Log in
              </Link>
              <Link
                to="/register"
                className="group flex items-center gap-1.5 rounded-full bg-[#131311] px-5 py-2.5 text-[13.5px] font-semibold text-white shadow-lg transition hover:bg-black"
              >
                Start free
                <ArrowUpRight size={15} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </Link>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-label="导航菜单"
          aria-expanded={open}
          className="grid h-10 w-10 place-items-center rounded-full border border-[#131311]/10 bg-white/80 md:hidden"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {open && (
        <div className="mx-4 mb-4 rounded-3xl border border-[#131311]/10 bg-white/95 p-3 shadow-2xl glass md:hidden">
          {!onAuthRoute &&
            LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold hover:bg-stone-100"
              >
                <link.icon size={17} className="text-stone-400" />
                {link.label}
                <span aria-hidden="true" className="text-xs font-normal text-stone-400">
                  · {link.cn}
                </span>
              </Link>
            ))}
          <div className="mt-2 grid gap-2 border-t border-stone-100 pt-3">
            {user ? (
              <button
                type="button"
                onClick={() => void auth.logout()}
                className="rounded-2xl bg-[#131311] px-4 py-3 text-sm font-bold text-white"
              >
                退出登录 · {user.nickname}
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Link
                  to="/login"
                  onClick={() => setOpen(false)}
                  className="rounded-2xl bg-stone-100 px-4 py-3 text-center text-sm font-bold"
                >
                  Log in
                </Link>
                <Link
                  to="/register"
                  onClick={() => setOpen(false)}
                  className="rounded-2xl bg-[#131311] px-4 py-3 text-center text-sm font-bold text-white"
                >
                  Start free
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
