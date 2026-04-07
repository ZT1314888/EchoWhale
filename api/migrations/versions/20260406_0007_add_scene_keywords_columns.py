"""add scene keyword columns"""

from alembic import op
import sqlalchemy as sa


revision = "20260406_0007"
down_revision = "20260405_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column("visual_anchors", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("vocab_candidates", sa.JSON(), nullable=False, server_default="[]")
        )

    op.execute("UPDATE sessions SET vocab_candidates = labels WHERE labels IS NOT NULL")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("visual_anchors", server_default=None)
        batch_op.alter_column("vocab_candidates", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("vocab_candidates")
        batch_op.drop_column("visual_anchors")
