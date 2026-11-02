import { Outlet, useLocation } from "react-router-dom";

import { Footer } from "./Footer";
import { Navbar } from "./Navbar";

/** 沉浸式路由：练习会话本身占满视口，页脚会让原本贴底的对话面板多出一段滚动。 */
function isImmersive(pathname: string) {
  return /^\/session\/[^/]+$/.test(pathname);
}

export function AppShell() {
  const location = useLocation();

  return (
    <div className="flex min-h-screen flex-col bg-[#f4f3ef] text-[#131311]">
      <Navbar />
      {/* 用 div 而非 main：每个页面自己已经渲染了一个 <main>，外壳再套一层会形成
          嵌套 landmark（且首页的 home-stage 是常驻的，不只是过渡态）。 */}
      <div className="flex-1">
        <Outlet />
      </div>
      {isImmersive(location.pathname) ? null : <Footer />}
    </div>
  );
}
