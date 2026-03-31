# Module Status: `platform_foundation`

## 基本信息

- `module`: `platform_foundation`
- `status`: `building`
- `branch`: `module/platform_foundation`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

承载 EchoWhale 的应用入口、配置、公共依赖、统一响应与共享底座，避免业务模块重复实现基础能力。

## 当前真相

- 现有实现：`api/main.py`、`api/core/`、`api/common/`、部分 `api/db/` 与 `api/integrations/` 底座已经存在
- 已完成边界：应用入口、基础配置、健康检查、CORS 配置
- 仍然缺失：更清晰的共享契约、更多基础回归测试、跨模块公共约束文档

## 输入输出契约

- 输入：环境变量、HTTP 请求、共享依赖配置
- 输出：应用配置对象、统一响应行为、共享底座能力
- 关键字段：`api_prefix`、`allowed_origins`、`llm_provider`

## 代码位置

- `api/main.py`
- `api/core/`
- `api/common/`
- 相关共享目录：`api/db/`、`api/integrations/`

## 当前工作

- `[ ]` 明确共享配置和依赖边界
- `[ ]` 补最小 smoke 验证
- `[ ]` 收敛底座层与业务层的职责边界

## 测试门

- `module_test_passed` 的标准：应用入口、配置读取、健康检查和基础依赖链路可验证
- 最少要覆盖的用例：配置加载、`/health`、基础启动
- 还没覆盖的风险：共享依赖扩展后可能出现边界漂移

## 阻塞项

- 当前测试骨架仍未展开，底座回归还需要补齐

## 变更记录

- `2026-03-30`：初始化模块状态文档
