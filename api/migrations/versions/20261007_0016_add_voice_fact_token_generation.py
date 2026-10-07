"""add voice_session_facts token_generation column"""

import sqlalchemy as sa
from alembic import op

revision = "20261007_0016"
down_revision = "20261006_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # think 代理令牌代数（审计 F12 Better fix）：每次 bootstrap +1，代理校验链
    # 要求令牌 gen claim 与该值一致，voice/complete 或 re-bootstrap 即令旧令牌
    # 失效。server_default 让迁移前的旧行（已收口/历史会话）落 0——语义是
    # "无活跃绑定"，与代理侧 fail-closed 校验自洽；列是纯附加物，回滚代码
    # 不感知该列，双向滚动部署安全。
    with op.batch_alter_table("voice_session_facts") as batch_op:
        batch_op.add_column(
            sa.Column("token_generation", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("voice_session_facts") as batch_op:
        batch_op.drop_column("token_generation")
