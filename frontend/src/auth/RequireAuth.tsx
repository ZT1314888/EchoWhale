import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthProvider";


export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const auth = useAuth();

  if (auth.status === "refreshing") {
    // 原位替代旧 `.empty-stage` 的整页居中舞台；h1 的字号沿用旧规则的 36px / 768px 以下 30px。
    return (
      <main className="flex min-h-[76vh] flex-col items-center justify-center">
        <h1 className="text-[36px] leading-[1.12] max-md:text-[30px]">正在恢复登录状态…</h1>
      </main>
    );
  }

  if (auth.status !== "authenticated") {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }

  return <>{children}</>;
}
