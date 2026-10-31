import { Link } from "react-router-dom";

import { Logo } from "./Logo";

const FOOTER_LINKS = [
  { to: "/", label: "Practice", cn: "练习" },
  { to: "/history", label: "Library", cn: "历史" },
  { to: "/progress", label: "Progress", cn: "进度" },
];

export function Footer() {
  return (
    <footer className="relative mt-14 overflow-hidden bg-[#131311] text-white">
      <div className="grid-pattern-light pointer-events-none absolute inset-0 opacity-40" />
      <div className="pointer-events-none absolute -right-24 -top-28 h-72 w-72 rounded-full bg-[#4f46e5]/25 blur-[110px]" />

      <div className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-9">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <Link to="/" className="group flex w-fit items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#d8f34e] transition-transform duration-300 group-hover:rotate-6">
              <Logo className="h-8 w-8" title="EchoWhale 品牌标志" />
            </span>
            <span className="leading-none">
              <span className="font-display block text-[17px] font-bold tracking-tight">EchoWhale</span>
              <span className="mt-1 block text-[9px] font-medium uppercase tracking-[0.16em] text-white/40">
                AI Speaking Coach
              </span>
            </span>
          </Link>

          <nav aria-label="页脚导航" className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {FOOTER_LINKS.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="text-[12.5px] font-semibold text-white/65 transition hover:text-[#d8f34e]"
              >
                {item.label}{" "}
                <span aria-hidden="true" className="text-[11px] font-normal text-white/35">
                  {item.cn}
                </span>
              </Link>
            ))}
          </nav>
        </div>

        <div className="mt-7 flex flex-col gap-1.5 border-t border-white/10 pt-5 text-[11px] text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 EchoWhale</p>
          <p>
            Speak with intention. <span className="text-white/25">·</span> 自信开口。
          </p>
        </div>
      </div>
    </footer>
  );
}
