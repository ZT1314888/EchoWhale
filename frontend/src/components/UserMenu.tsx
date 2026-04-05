import { useEffect, useRef, useState, type FocusEvent } from "react";

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

  if (!auth.user) {
    return null;
  }

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

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
