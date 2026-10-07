// ESLint flat config（package.json 有 "type": "module"，本文件按 ESM 加载）。
// 起步预设：typescript-eslint recommended + react-hooks recommended-latest
// （含 exhaustive-deps）+ react-refresh（Vite 项目 HMR 边界检查）。
// 规则约束：禁止全局关闭任何规则；项目专属豁免只能按文件逐条写，并附理由。
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  // 全局忽略：构建产物与覆盖率报告，不属于源码 lint 范围（node_modules 默认忽略）。
  { ignores: ["dist/**", "coverage/**"] },

  // TS 语法 + TS 版通用规则；项目 strict TS 且零 any，recommended 不放水。
  ...tseslint.configs.recommended,

  // react-hooks v7 flat 预设：rules-of-hooks / exhaustive-deps 及 compiler 系规则。
  // exhaustive-deps 预设是 warn，这里升为 error——lint 门禁要求零 warning，
  // hooks 依赖数组错误正是本门禁要拦的主要回归类型。
  reactHooks.configs.flat["recommended-latest"],
  { rules: { "react-hooks/exhaustive-deps": "error" } },

  // react-refresh：Vite 项目的 fast-refresh 边界检查（vite 预设允许常量导出）。
  reactRefresh.configs.vite,

  // ---------------------------------------------------------------------------
  // 项目专属豁免（逐条写理由，对齐 pyproject ruff ignore 的注释风格）
  // ---------------------------------------------------------------------------

  // 测试与测试工具文件不参与 fast-refresh 边界：测试文件常需导出 helper/
  // mock 工厂，按组件边界约束它们只会逼出无意义的文件拆分。
  {
    files: ["src/**/*.test.ts", "src/**/*.test.tsx", "src/test/setup.ts"],
    rules: { "react-refresh/only-export-components": "off" },
  },

  // AuthProvider.tsx 同时导出 Provider 组件与 useAuth hook：auth context 的
  // 既有组织方式（消费方从同一路径取 hook 与 Provider），hook 与组件同文件不
  // 破坏 fast-refresh 本身；拆文件属跨 10+ 处 import 的纯 churn，留给独立重构批次。
  {
    files: ["src/auth/AuthProvider.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
);
