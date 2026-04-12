# EchoWhale Agent Governance

## 目标

这份文档描述 EchoWhale 当前 agent 治理体系的一期收口方式：

- `docs/control/agent-control-plane.json` 是控制面单一事实源
- `docs/control/project-index.md` 是人类可读的工作台视图，其中生成区块由事实源渲染
- `.codex/README.md` 是 repo-local agent 工作台入口
- `tools/agent_ops.py` 提供最小协作命令入口

## 单一事实源

以下内容必须先更新事实源，再渲染到视图页：

- `system` 总状态
- 最新进度快照摘要
- 模块看板
- 模块清单
- 关键 feature 列表
- 测试层状态

不要直接手改 `project-index.md` 的生成区块，否则 `uv run python -m tools.agent_ops check` 会报 drift。

## 人工维护内容

以下内容仍由人维护，不自动生成：

- `project-index.md` 的状态词、分支约定、合并规则和当前优先级
- 各模块 `status.md` 的详细边界、风险和变更记录
- feature / bug / version 文档里的背景、验收、验证结果

## 命令入口

### 1. 校验

```powershell
uv run python -m tools.agent_ops check
```

用途：检查状态值、关键文档存在性，以及 `project-index.md` 生成区块是否与事实源一致。

### 2. 渲染

```powershell
uv run python -m tools.agent_ops render
```

用途：从事实源重建 `project-index.md` 生成区块。

### 3. 脚手架

```powershell
uv run python -m tools.agent_ops bootstrap feature agent_governance_control_plane --module platform_foundation --owner codex
```

用途：从模板生成治理文档骨架，减少手写元数据漂移。

## 日常流程

1. 确认这次工作影响的是 feature、bug、module 还是 version。
2. 需要新文档时，用 `bootstrap` 生成骨架。
3. 修改状态或索引信息时，先改 `agent-control-plane.json`。
4. 运行 `render` 更新 `project-index.md`。
5. 运行 `check` 确认控制面一致。
6. 再进行代码、测试和详细文档更新。

## 二期技术债

以下问题已知存在，但不在本期治理收口里直接重构：

- `api/modules/session_engine/agent.py` 仍有基于 `inspect.signature(...)` 的兼容分派逻辑
- `api/contracts/history.py` 仍直接依赖 `api.modules.session_engine.review_builder`
- 若后续要强化子代理并行治理，需要把共享控制文件的不可并行约束继续工具化
