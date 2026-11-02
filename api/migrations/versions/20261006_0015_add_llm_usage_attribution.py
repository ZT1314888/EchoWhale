"""add llm usage attribution columns"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0015"
down_revision = "20261006_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 用量归因列（request-id 上下文批次后的收尾）：owner 形如 user:<uuid> /
    # visitor:<uuid>，session 形如 sess_<uuid>，128 列宽对两种形态留余量。
    # 两列可空——旧行与无请求上下文的写入路径（后台任务、session_start 创建前
    # 的 LLM 调用）保持 NULL 天然兼容；本批次只写不读，归因查询按 created_at
    # 既有索引起步，查询需求出现时再补索引，避免过早优化。
    with op.batch_alter_table("llm_usage") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("session_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("llm_usage") as batch_op:
        batch_op.drop_column("session_id")
        batch_op.drop_column("owner_id")
