# 会话写路径完整性与追加语义（session_write_integrity）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 7 / Finding 8 修复。
> Trellis 任务：`.trellis/tasks/10-01-session-write-integrity`。

## 目标

`save_reply_turn` 用 `max(position)+1` 分配序号且数据库层无唯一约束——同会话并发回复产生重复 position，回放错乱、分页游标丢消息；`finalize_voice_session` 是"全量删除重写"，语音收口与文本轮并发时静默删掉对方刚落库的消息（丢失更新）。

## 实现说明

### 1. 迁移 20261001_0011

- `session_messages` 增加 `uq_session_messages_session_position` UNIQUE(session_id, position)——SQLite 走 batch_alter_table（表复制），PG 为普通 DDL；down 可逆。
- `sessions` 补 `ix_sessions_user_id_updated_at` 复合索引（历史列表 keyset 分页的过滤 + 排序都走索引）。
- 部署注意：若生产已有重复 position 数据，建约束前需先清理（当前无生产数据，未内置自动清理）。

### 2. save_reply_turn 冲突重试（Finding 7）

每次尝试独立事务：`IntegrityError`（SQLite 在 commit 时、PG 在 flush 时抛）→ 整体回滚重开 → 重读 max(position) 重试一次；二次冲突抛 `InvalidStateError("Concurrent reply write conflict")`。`_read_max_position` 抽为独立方法，同时是重试测试的确定性缝隙（伪造过期 max 读值复现竞态，无需真实线程）。

### 3. 语音收口 append-only（Finding 8）

`finalize_voice_session` 签名增加 `new_messages`：agent 层 `_build_voice_messages` 已算好尾段去重（`remainder[overlap:]`），仓储只从当前 max+1 连续追加新增部分，**既有消息行一律不动**（SQL 监听器测试断言路径中无 DELETE FROM session_messages）。review / voice fact / events 仍在同一事务 upsert。`save_session` 的 delete-重写实现保留但 docstring 标明仅限创建路径（创建时无并发写者）。

## 验证

- 5 个新回归测试：约束拒绝重复 position（DB 级）、重试成功路径（position 0,1,2,3 + warning 日志）、双冲突 → InvalidStateError、finalize append-only（消息 id 集不变 + position 连续 + 无 DELETE）、迁移 up/down 可逆（真实 SQLite 文件跑完整 alembic 链）。
- `uv run pytest tests -q`：393 passed / 2 skipped；ruff / black 全绿。

## 遗留

- `add_message`（单条追加）仍无重试——当前无生产调用方（reply 走 save_reply_turn），随调用方出现再补。
- Finding 9（历史列表 INNER JOIN 语义）另行决策；乐观锁版本列（审计 Better fix）仅在约束+重试不足时考虑。
