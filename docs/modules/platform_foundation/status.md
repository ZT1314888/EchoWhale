# Module Status: `platform_foundation`

## 基本信息

- `module`: `platform_foundation`
- `status`: `building`
- `branch`: `module/platform_foundation`
- `owner`: `codex`
- `updated_at`: `2026-04-10`

## 模块目标

承载 EchoWhale 的应用入口、配置、公共依赖、统一响应与共享底座，并负责 repo-local agent 治理入口，避免业务模块重复实现基础能力或重复维护控制面状态。

## 当前真相

- 现有实现：`api/main.py`、`api/core/`、`api/common/`、部分 `api/db/` / `api/integrations/` 共享底座已经存在；本轮新增 `tools/agent_ops.py`、控制面事实源与工作台文档。
- 已完成边界：应用入口、基础配置、健康检查、CORS 配置、`/api/v1/*` 统一响应壳与全局异常处理；repo-local `check / render / bootstrap` 命令入口已落地。
- 当前响应规范：业务 API 成功返回 `code/message/data`，失败返回 `code/message`，请求校验错误也会进入统一响应壳；`/health` 继续保留裸响应 `{"status":"ok"}`。
- 仍然缺失：更强的 smoke 自动化、更多共享依赖边界回归，以及控制面到子代理并行规则的进一步工具化。

## 输入输出契约

- 输入：环境变量、HTTP 请求、共享依赖配置、agent 控制面事实源
- 输出：应用配置对象、统一响应行为、共享底座能力、repo-local 治理命令
- 关键字段：`api_prefix`、`allowed_origins`、`llm_provider`

## 代码位置

- `api/main.py`
- `api/core/`
- `api/common/`
- `tools/agent_ops.py`
- `docs/control/agent-control-plane.json`
- 相关共享目录：`api/db/`、`api/integrations/`

## 当前工作

- `[x]` 接入 EchoWhale 版 `ApiResponse` 并在应用层挂载全局异常处理
- `[x]` 明确 `/api/v1/*` 与 `/health` 的响应边界
- `[x]` 为控制面补单一事实源、生成视图和 repo-local 校验命令
- `[ ]` 补最小 smoke 验证
- `[ ]` 收敛底座层与业务层的职责边界

## 测试门

- `module_test_passed` 的标准：应用入口、配置读取、健康检查、治理命令和基础依赖链路可验证
- 最少要覆盖的用例：配置加载、`/health`、`tools.agent_ops check/render/bootstrap`
- 还没覆盖的风险：共享依赖扩展或控制面字段增多后可能出现边界漂移

## 阻塞项

- 当前 smoke 和更完整的共享底座回归仍需继续补齐

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-04-02`：对齐 `Fastapi-template` 响应体规范，补齐 EchoWhale 统一响应模型、全局异常处理和 `/health` 例外约定
- `2026-04-10`：新增 agent 控制面事实源、生成视图与 repo-local 治理命令入口
