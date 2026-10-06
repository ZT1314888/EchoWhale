# EchoWhale Agent Entry

本仓库的代理协作文档统一放在 `docs/`，与主追踪系统同库维护。

## 读取顺序

1. 当前会话中用户的明确要求
2. [`docs/prd.md`](docs/prd.md)
3. [`docs/control/project-index.md`](docs/control/project-index.md)
4. [`docs/control/agent-governance.md`](docs/control/agent-governance.md)
5. 全局 `AGENTS.md`

## 本仓库的最小硬规则

- 这是一个后端 scaffold 已存在、前端与测试仍以骨架为主的项目。
- 实现类任务默认要走模块归属、文档留痕、分层测试和合并门禁。
- `docs/` 是主追踪系统；不要只改代码不更新记录，除非用户明确允许。
- 详细执行协议、门禁与控制面操作见 [`docs/control/agent-governance.md`](docs/control/agent-governance.md)；状态词、分支约定以 [`docs/control/project-index.md`](docs/control/project-index.md) 渲染块为准。

## 说明

- 根目录保留此文件，是为了让项目级规则入口保持显式、稳定、易发现。
- 协议细节集中在 `docs/control/` 下维护，不另设第二份协议文档。
