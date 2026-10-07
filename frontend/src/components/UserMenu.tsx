import { useEffect, useRef, useState, type FocusEvent } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

type UserMenuProps = {
  variant?: "default" | "home";
};

const CLOSE_DELAY_MS = 120;

export function UserMenu({ variant = "default" }: UserMenuProps) {
  const auth = useAuth();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  // 卸载时清掉未触发的关闭定时器。必须放在 `!auth.user` 早退之前：
  // hooks 只能在每次渲染都以相同顺序调用，早退后再调用会在登录态
  // 从无到有的那次渲染里改变 hook 数量，直接触发 React 运行时错误。
  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  if (!auth.user) {
    return null;
  }

  function cancelScheduledClose() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function openMenu() {
    cancelScheduledClose();
    setOpen(true);
  }

  function closeMenu() {
    cancelScheduledClose();
    setOpen(false);
  }

  function scheduleClose() {
    cancelScheduledClose();
    closeTimerRef.current = setTimeout(() => {
      setOpen(false);
      closeTimerRef.current = null;
    }, CLOSE_DELAY_MS);
  }

  function onBlur(event: FocusEvent<HTMLDivElement>) {
    if (containerRef.current?.contains(event.relatedTarget as Node | null)) {
      return;
    }
    closeMenu();
  }

  async function onLogout() {
    setLoggingOut(true);
    try {
      await auth.logout();
      closeMenu();
    } finally {
      setLoggingOut(false);
    }
  }

  const triggerClassName =
    variant === "home" ? "user-menu__trigger user-menu__trigger--home" : "user-menu__trigger ghost-button";

  return (
    <div
      ref={containerRef}
      className={`user-menu user-menu--${variant}`}
      onBlur={onBlur}
      onFocus={openMenu}
      onMouseEnter={openMenu}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        className={triggerClassName}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {auth.user.nickname}
      </button>

      {open ? (
        <div className="user-menu__panel" role="menu" aria-label="账号菜单">
          {/* 导航入口用 Link 而非 button：语义是页面跳转（可新标签打开、可中键点击），退出登录才是动作类按钮。 */}
          <Link className="user-menu__item" role="menuitem" to="/progress" onClick={closeMenu}>
            我的进度
          </Link>
          <button
            type="button"
            className="user-menu__item"
            role="menuitem"
            onClick={onLogout}
            disabled={loggingOut}
          >
            {loggingOut ? "退出中…" : "退出登录"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
