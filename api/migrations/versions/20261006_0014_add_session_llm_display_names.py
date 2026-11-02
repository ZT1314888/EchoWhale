"""add session llm display name columns"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0014"
down_revision = "20261002_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # LLM 复盘展示名（ReviewCopy.scene_title / role_label）随回复轮与语音收口
    # 落库（PRD v0.5 候选②）：两列可空——旧行读出 None 时消费侧自动走确定性
    # 展示名路径（resolver 字段级回退），天然向后兼容；cap 40 列宽 64 留余量。
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("llm_scene_title", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("llm_role_label", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("llm_role_label")
        batch_op.drop_column("llm_scene_title")
