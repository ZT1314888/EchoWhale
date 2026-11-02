import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8001";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      coverage: {
        provider: "v8",
        include: ["src/**"],
        exclude: ["src/main.tsx", "src/test/**", "src/vite-env.d.ts", "**/*.d.ts"],
        reporter: ["text", "html"],
        thresholds: {
          // 基线（2026-09-30 实测）：Stmts 78.9 / Branch 76.4 / Funcs 81.8 / Lines 78.9，
          // 阈值取基线下方 2-3 个点作为防回归底线，不作为目标值。
          statements: 76,
          branches: 74,
          functions: 78,
          lines: 76,
        },
      },
    },
  };
});
