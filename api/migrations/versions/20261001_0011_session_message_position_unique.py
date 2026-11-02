"""session_messages position unique constraint and sessions history index"""

from alembic import op

revision = "20261001_0011"
down_revision = "20260930_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史列表查询按 (user_id, updated_at DESC, id DESC) 做 keyset 分页，
    # 复合索引让过滤与排序都走索引，避免随消息量增长的全表扫描。
    op.create_index("ix_sessions_user_id_updated_at", "sessions", ["user_id", "updated_at"])
    # position 唯一性是数据库级兜底：任何写路径并发分配 max+1 都会撞约束而不是静默重复。
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，batch 模式借表复制完成；
    # Postgres 下 batch 默认即普通 DDL，行为一致。
    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.create_unique_constraint(
            "uq_session_messages_session_position", ["session_id", "position"]
        )


def downgrade() -> None:
    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.drop_constraint("uq_session_messages_session_position", type_="unique")
    op.drop_index("ix_sessions_user_id_updated_at", table_name="sessions")
