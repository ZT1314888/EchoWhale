"""create user_learning_profiles table"""

import sqlalchemy as sa
from alembic import op

revision = "20261002_0013"
down_revision = "20261002_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 学员学习档案（每认证用户一行）：从每轮 FeedbackResult 已产出的信号
    # （9 类封闭错误分类 + CEFR 估计）零额外 LLM 成本地滚动累积学员状态。
    # JSON 列全部写侧封顶（≤9 / ≤12 / ≤10），行宽有界；visitor:* 不建档，
    # 由编排层 user_id 前缀门控保证，因此 user_id 无需 FK。
    op.create_table(
        "user_learning_profiles",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("cefr_estimate", sa.String(length=2), nullable=True),
        sa.Column("error_type_counts", sa.JSON(), nullable=False),
        sa.Column("scene_counts", sa.JSON(), nullable=False),
        sa.Column("cefr_history", sa.JSON(), nullable=False),
        sa.Column("practiced_turn_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_learning_profiles")
