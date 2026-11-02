"""create llm_usage table"""

import sqlalchemy as sa
from alembic import op

revision = "20261002_0012"
down_revision = "20261001_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # LLM 用量账本（Finding 10b）：每次调用按 model 记一行 token 消耗，
    # 回答"账单为什么涨"只需要按天/按模型聚合。owner/session 归因列由
    # 迁移 0015 补齐（0012 落地时归因暂缓，后续批次已跟进）。
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # 按天聚合查询走 created_at 索引；SQLite 与 Postgres 均支持 CURRENT_TIMESTAMP 默认值。
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_table("llm_usage")
