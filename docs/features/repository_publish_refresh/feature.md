# Feature: `repository_publish_refresh`

## 基本信息

- `feature`: `repository_publish_refresh`
- `status`: `feature_test_passed`
- `branch`: `feature/repository-publish-refresh`
- `module`: `platform_foundation`
- `cross_module`: `yes`
- `owner`: `codex`
- `updated_at`: `2026-11-02`
- `merge_target`: `dev`

## 背景与范围

GitHub main 落后 dev 53 个提交，README 与截图未反映新版产品，历史审计尚未归档。
本批次以 origin/dev 的 3309043 为基线，整理展示与发布门禁后通过 dev → main 发布。
主责任模块为 platform_foundation；frontend_app 联动 Bundler 配置、生产构建与页面截图，
infra_delivery 联动 CI 证据。属于配置与交付文档整理，不修改业务 API、数据契约或迁移。

## 设计与验收

- 保留 npm/package-lock.json 与本地 Bundler 修改；前端 CI 补生产构建。
- 两个后端 CI job 的 pytest 进程以 60 秒硬超时运行，四个 job 与覆盖率阈值保持。
- 历史审计归档 docs/audits/，标注历史日期并修正引用；本机元数据、编辑器与浏览器快照仅忽略。
- README 按已实现能力重写，三张截图来自隔离数据库、mock provider 与真实页面。
- 浏览器完成示例创建、三轮文字回复、复盘概览，检查桌面/手机布局与控制台。
- 不删除历史分支、不处理 PR #2、不改其他 worktree；不改现有开发数据库。
- 整理 PR → dev，发布 PR dev → main，检查通过后 merge commit 合并；main 精确 SHA 的四项 CI 全绿。
- GitHub About 同步，最终本地 dev/main 快进并停留 main，工作区干净。

## 验证记录

- 前端：npm ci（按锁文件安装），npm run coverage：31 文件、189 测试通过；语句/分支/函数/行覆盖率 90.01/82.95/85.27/90.01%，保持阈值 76/74/78/76%。随后 lint、typecheck、build 均通过。
- 后端：独立 SQLite 测试库，subprocess.run(timeout=60) 约束 pytest；692 passed / 5 skipped，覆盖率 90.80% ≥ 87%，耗时 40.94 秒。保留 6 条既有资源/协程警告。PostgreSQL 平价与迁移往返交由 CI job 验证。
- ruff check api tests tools、black --check api tests tools、agent_ops render/check 均通过。
- 首次沙箱运行因 uv 缓存、pytest 临时目录、Node realpath 权限失败；沙箱内后端测试触发 60 秒硬超时退出。按权限规则在沙箱外重跑通过，没有忽略失败或改动业务实现。
- 演示：独立 tmp/publish-refresh/demo.db，MODEL_RUNTIME_MODE=mock、REDIS_URL 置空；后端 8011、前端 5174。使用 create_all 准备演示 SQLite 模型，不连接原开发数据库，不用迁移往返工具。
- Playwright MCP 操作真实页面：咖啡店示例 → 场景就绪 → 进入练习 → 三轮英文回复（/reply/stream 均 200）→ 直接进入复盘地址。复盘含最后一句回复与反馈/词汇，三张桌面截图已替换；未注入前端数据或改造页面。
- 桌面 1440×1000：三页均无横向溢出。手机 375×812：练习/复盘无横向溢出；首页 document.scrollWidth=429，存在既有横向溢出（配置区内容超宽），本轮只记录，不修改 UI。手机截图保留于忽略目录 tmp/publish-refresh/。
- 控制台：匿名 auth/refresh 与 history/messages 返回 401；无其他应用异常。匿名逐字稿不可用，不计为验证通过。
截图使用演示数据。既有边界：文字练习无复盘跳转按钮，复盘直接访问地址；匿名逐字稿受认证限制，不计为验证通过。
CI 验证构建，尚未配置 CD；本批次不宣称真实语音与外部模型联调通过。

## 发布证据

- GitHub About 已核对为“图片驱动的英语情景陪练，支持实时语音、即时反馈与学习复盘”。
- 三组提交：5854850（配置与 CI）、444169a（审计归档）、22c5735（README、截图与治理）。
- [整理 PR #5](https://github.com/ZT1314888/EchoWhale/pull/5)：[四项 CI 全绿](https://github.com/ZT1314888/EchoWhale/actions/runs/41448719386)，无未解决讨论，merge commit 58a5772d5ce1a692d5bad6434f3629715ff94285 合入 dev。
- [dev → main 发布 PR #6](https://github.com/ZT1314888/EchoWhale/pull/6)：本条记录随 dev 提交进入发布 PR，最终 head 的检查、管理员合并、准确 main SHA 与合并后 CI 验收证据保存在该 PR 时间线，避免在提交中自引用未来合并 SHA。
- main 的规则集要求一人批准，允许仓库管理员豁免；按本轮授权，仅在最终检查全绿且讨论解决后使用 --admin --merge，不关闭保护规则、不强推、不删除分支。
- [主线 CI 记录](https://github.com/ZT1314888/EchoWhale/actions/workflows/ci.yml?query=branch%3Amain)：四个 job 验证测试、迁移与构建；尚未配置 CD。
- 控制面先更新事实源，再 render/check；保留原 system=integrating 与其他模块状态，不将 mock 冒烟等同于完整生产联调。
