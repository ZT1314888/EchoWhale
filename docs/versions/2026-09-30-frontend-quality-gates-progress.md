# 2026-09-30 前端质量门禁（tsc 清零 + SSE 读取器清理 + CI）进度

第五批（质量门禁批次）完成：`npx tsc --noEmit` **0 error**（批前 14），前端 vitest **99 passed**（基线 98 + 新增 1），后端 `uv run pytest tests` **224 passed / 2 skipped**（零回归）；且在无 .env、仅注入 `DATABASE_URL`（sqlite）+ 预建表的环境下同样 **224 passed / 2 skipped**——CI 配方已逐字本地验证。仓库首次具备 CI。

## tsc 清零（14 → 0）

- `tsconfig.json` target/lib 升 ES2022：一次消除 5 处 `.at()` 误报（App.test、mockApi.test×3、useDeepgramVoiceAgent）
- 新增 `frontend/src/vite-env.d.ts`（`/// <reference types="vite/client" />`）：消除 mockApp.ts 3 处静态图片导入报错
- `apiClient.ts`：请求对象 `credentials: "include" as const`——对象展开会把字面量宽化成 string，重试分支是内联字面量所以只有主请求需要
- `sessionApi.ts`：`submitPracticeTurnStream` 的 `let finalData/streamError` 在 SSE 回调闭包里赋值，控制流分析把它们收窄成 `never`（三处误报）——改为属性 holder（属性收窄会被中间的 await 调用重置）+ `const` 提取后判空
- `practiceApi.ts`：示例场景参数用 `SAMPLE_SCENE_IDS as const` 白名单 + `isSampleSceneId(value: string | undefined)` 类型守卫收窄（守卫内部先 `typeof` 判 string 再 includes）
- `package.json` 新增 `typecheck` 脚本

## SSE 读取器清理（消费兜底）

- `consumeSseResponse` 的读取循环包进 `try/finally`，退出时 `await reader.cancel().catch(() => {})`：文字回合中途 AbortSignal 取消或断流时，read() 抛出会直接跳过原来的 `releaseLock()`——现在锁与流必然释放；正常结束（done）后 cancel 幂等无害
- 新增测试「cancels the reader when the stream fails mid-flight」：controller.error 模拟中途失败，断言原始错误透传（页面靠 `name === "AbortError"` 区分取消）+ `ReadableStreamDefaultReader.prototype.cancel` 被调用
- 语义澄清：流已 errored 时 cancel 不再触发底层 source.cancel，所以断言 spy 公开方法而不是底层回调

## 顺手修掉的测试密闭性缺口（CI 逼出来的）

- `tests/modules/test_scene_cache.py` 两个 live 分流用例此前隐式依赖本机 .env 的真实供应商配置（live 构造要求至少一个"真实"槽位，env 缺席时 `resolve_engine_providers` 直接抛 ConfigurationError）——在用例内 monkeypatch vision + text 主槽位的 dummy 值（两个用例随后都把 scene_engine 换成 fake，真实客户端不会被调用），测试从此不依赖本机密钥
- 应用级路由隐式依赖已迁移库：CI 方案为 sqlite + `create_all_tables_async` 预建表（工作流内 python heredoc 原样执行），无需 postgres service 容器，且与全套 aiosqlite 测试的方言兼容性一致
- 全套本地探针跑下来，无 .env 时 38 failed 的根因就是上面两条，修完后 CI 与本地同为全绿

## CI（仓库首个 workflow）

- `.github/workflows/ci.yml`：`backend`（setup-uv + `uv sync --frozen` + `uv run pytest tests`）与 `frontend`（node 22 + `npm ci` + `npm run typecheck` + `npm test`）双 job 并行；concurrency 按 ref 取消旧跑；npm/uv 均启用缓存
- `uv lock --check` 通过，`--frozen` 成立；CI 无 .env 文件，`MODEL_RUNTIME_MODE` 落在默认 mock，测试前提天然满足（对应陷阱 #3 的 CI 形态）

## 过程要点

- heredoc 传输会吞反斜杠：测试里的 `"\n\n"` 转义被 heredoc 展开成真实换行导致 TS 语法错误（tsc 定位到行），改走「Write 落补丁文件 + count 断言」后修复——长补丁一律不用内联 heredoc，与第四批结论一致
- 类型守卫两段式：先放宽签名接受 `string | undefined`（tsc 暴露第二处），再在守卫体内 `typeof` 收窄——一次只改一处会被 tsc 逼出下一层

## 留守事项

- vitest coverage 阈值、ruff/black 接入 CI（下一批可顺手）
- P1 体验项未动：加载页真实进度 + 取消等待、语音回合反馈卡统一（见第四批评估清单）
- 上批遗留照旧：`SCENE_ANALYSIS_ASYNC_ENABLED` 生产开启前确认 worker 消费；PRD 待刷新
